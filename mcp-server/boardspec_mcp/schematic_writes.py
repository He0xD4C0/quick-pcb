"""Checked schematic primitive mutations."""

from __future__ import annotations

import json
import re

from .schematic_bridge import (
    _execute,
    component_create_program,
    component_edit_program,
    component_remove_program,
    marker_edit_program,
    marker_program,
    no_connect_program,
    wire_create_program,
    wire_edit_program,
)
from .schematic_codec import require_grid
from .schematic_routing import path_is_clear, route_orthogonal
from .schematic_tools import _checked_write, _error, _state

PIN_SELECTOR = re.compile(r"^(.+)\.#([^#]+)$")


def _validate_grid(items, keys=("x", "y")):
    try:
        for item in items:
            for key in keys:
                if item.get(key) is not None:
                    require_grid(item[key])
    except ValueError as exc:
        return _error("COORDINATE_OFF_GRID", str(exc))
    return None


def _component_matches(found: dict, wanted: dict) -> bool:
    identity = found.get("component") or {}
    return identity.get("libraryUuid") == wanted.get("library_uuid") and (
        identity.get("uuid") == wanted.get("device_uuid")
        or bool(wanted.get("device_name") and identity.get("name") == wanted.get("device_name"))
    )


def place_schematic_components(client, window_id, expected_context_revision, expected_revision, placements):
    if error := _validate_grid(placements):
        return error
    state, _, error = _state(client, window_id)
    if error:
        return error
    current = {item.get("designator"): item for item in state["components"]}
    pending = []
    for item in placements:
        found = current.get(item["designator"])
        if found:
            if _component_matches(found, item):
                continue
            return _error("DESIGNATOR_CONFLICT", f"{item['designator']} is occupied by another device")
        pending.append(item)
    if not pending:
        return {
            "ok": True, "applied": False,
            "unchanged": [item["designator"] for item in placements],
            "context_revision": state["context_revision"],
            "revision_before": state["revision"], "revision_after": state["revision"],
        }
    return _checked_write(client, window_id, expected_context_revision, expected_revision, component_create_program(pending))


def set_schematic_component_placement(client, window_id, expected_context_revision, expected_revision, edits):
    state, _, error = _state(client, window_id)
    if error:
        return error
    current = {item.get("designator"): item for item in state["components"]}
    prepared = []
    for edit in edits:
        found = current.get(edit["designator"])
        if not found:
            return _error("COMPONENT_NOT_FOUND", f"{edit['designator']} was not found")
        props = {key: value for key, value in edit.items() if key != "designator"}
        if error := _validate_grid([props]):
            return error
        prepared.append({"id": found["id"], "designator": edit["designator"], "properties": props})
    return _checked_write(client, window_id, expected_context_revision, expected_revision, component_edit_program(prepared))


def remove_schematic_components(client, window_id, expected_context_revision, expected_revision, removals, confirm_topology_change=False):
    if not confirm_topology_change:
        return _error("CONFIRMATION_REQUIRED", "confirm_topology_change=true is required")
    state, _, error = _state(client, window_id)
    if error:
        return error
    known = {item["id"] for item in state["components"]}
    ids = [item["id"] for item in removals]
    if missing := sorted(set(ids) - known):
        return _error("PRIMITIVE_NOT_FOUND", "component primitive IDs not found", ids=missing)
    return _checked_write(client, window_id, expected_context_revision, expected_revision, component_remove_program(ids))


def _pin_point(state, selector):
    match = PIN_SELECTOR.fullmatch(selector)
    if not match:
        return None, _error("INVALID_PIN_SELECTOR", f"pin selector must be DESIGNATOR.#PIN: {selector}")
    designator, number = match.groups()
    matches = [item for item in state["components"] if item.get("designator") == designator]
    if len(matches) != 1:
        return None, _error("COMPONENT_NOT_FOUND", f"expected one {designator} component")
    pins = [pin for pin in matches[0].get("pins", []) if str(pin.get("number")) == number]
    if len(pins) != 1 or pins[0].get("x") is None or pins[0].get("y") is None:
        return None, _error("PIN_NOT_FOUND", f"exact pin {selector} was not found")
    return {"x": pins[0]["x"], "y": pins[0]["y"]}, None


def _point(state, value):
    return _pin_point(state, value) if isinstance(value, str) else (value, None)


def create_schematic_wires(client, window_id, expected_context_revision, expected_revision, wires):
    state, _, error = _state(client, window_id)
    if error:
        return error
    prepared, occupied = [], list(state["wires"])
    for item in wires:
        for branch in item["branches"]:
            start, error = _point(state, branch["start"])
            if error:
                return error
            end, error = _point(state, branch["end"])
            if error:
                return error
            if any(
                existing.get("net") == item["net"]
                and len(existing.get("points", [])) >= 2
                and {(existing["points"][0]["x"], existing["points"][0]["y"]),
                     (existing["points"][-1]["x"], existing["points"][-1]["y"])}
                == {(start["x"], start["y"]), (end["x"], end["y"])}
                for existing in state["wires"]
            ):
                continue
            points = [start, *branch.get("waypoints", []), end]
            unrelated = [wire for wire in occupied if wire.get("net") != item["net"]]
            if branch.get("role"):
                routed = points if path_is_clear(points, state["components"], unrelated) else None
            else:
                routed = route_orthogonal(points, state["components"], unrelated)
            if not routed:
                return _error("ROUTE_BLOCKED", f"no obstacle-free orthogonal route for {branch['client_id']}; use net labels or ports")
            if error := _validate_grid(routed):
                return error
            canonical = json.dumps(routed, sort_keys=True)
            duplicate = any(
                existing.get("net") == item["net"]
                and json.dumps(existing.get("points"), sort_keys=True)
                in {canonical, json.dumps(list(reversed(routed)), sort_keys=True)}
                for existing in state["wires"]
            )
            if not duplicate:
                value = {"client_id": branch["client_id"], "net": item["net"], "points": routed}
                prepared.append(value)
                occupied.append(value)
    if not prepared:
        return {
            "ok": True, "applied": False, "unchanged": True,
            "context_revision": state["context_revision"],
            "revision_before": state["revision"], "revision_after": state["revision"],
        }
    return _checked_write(client, window_id, expected_context_revision, expected_revision, wire_create_program(prepared))


def edit_schematic_wires(client, window_id, expected_context_revision, expected_revision, actions):
    state, _, error = _state(client, window_id)
    if error:
        return error
    known = {item["id"] for item in state["wires"]}
    if missing := sorted({item["id"] for item in actions} - known):
        return _error("PRIMITIVE_NOT_FOUND", "wire primitive IDs not found", ids=missing)
    for action in actions:
        points = (action.get("properties") or {}).get("points")
        if points:
            if error := _validate_grid(points):
                return error
            if any(a["x"] != b["x"] and a["y"] != b["y"] for a, b in zip(points, points[1:])):
                return _error("WIRE_PATH_INVALID", "wire segments must be horizontal or vertical")
    return _checked_write(client, window_id, expected_context_revision, expected_revision, wire_edit_program(actions))


def _place_markers(client, kind, window_id, expected_context_revision, expected_revision, items):
    state, _, error = _state(client, window_id)
    if error:
        return error
    if kind == "label":
        response = _execute(client, "return eda.sys_Environment.getEditorCurrentVersion(true);", window_id)
        if not response.get("ok"):
            return response
        version = str(response.get("result") or "0")
        try:
            major = int(version.split(".", 1)[0])
        except ValueError:
            major = 0
        if major < 4:
            return _error("API_UNAVAILABLE", "createNetLabel requires EasyEDA Pro v4 or newer; use net ports on v3", editor_version=version)
    prepared = []
    existing = state[{"label": "labels", "port": "ports", "flag": "flags"}[kind]]
    for item in items:
        point, error = _point(state, item["at"])
        if error:
            return error
        value = {**item, **point}
        value.pop("at", None)
        if not any(marker.get("net") == value.get("net") and marker.get("x") == value.get("x") and marker.get("y") == value.get("y") for marker in existing):
            prepared.append(value)
    if error := _validate_grid(prepared):
        return error
    if not prepared:
        return {
            "ok": True, "applied": False, "unchanged": True,
            "context_revision": state["context_revision"],
            "revision_before": state["revision"], "revision_after": state["revision"],
        }
    return _checked_write(client, window_id, expected_context_revision, expected_revision, marker_program(kind, prepared))


def place_schematic_net_labels(client, *args):
    return _place_markers(client, "label", *args)


def place_schematic_net_ports(client, *args):
    return _place_markers(client, "port", *args)


def place_schematic_net_flags(client, *args):
    return _place_markers(client, "flag", *args)


def edit_schematic_net_markers(client, window_id, expected_context_revision, expected_revision, actions, confirm_topology_change=False):
    state, _, error = _state(client, window_id)
    if error:
        return error
    if len({item["id"] for item in actions}) != len(actions):
        return _error("DUPLICATE_PRIMITIVE_ID", "marker actions must use unique primitive IDs")
    by_kind = {
        "label": {item["id"]: item for item in state["labels"]},
        "port": {item["id"]: item for item in state["ports"]},
        "flag": {item["id"]: item for item in state["flags"]},
    }
    missing = [item["id"] for item in actions if item["id"] not in by_kind[item["kind"]]]
    if missing:
        return _error("PRIMITIVE_NOT_FOUND", "marker primitive IDs not found", ids=sorted(missing))
    if any(item["op"] == "delete" for item in actions) and not confirm_topology_change:
        return _error("CONFIRMATION_REQUIRED", "confirm_topology_change=true is required for marker deletion")
    if any((item.get("replacement") or {}).get("kind") == "label" for item in actions):
        response = _execute(client, "return eda.sys_Environment.getEditorCurrentVersion(true);", window_id)
        if not response.get("ok"):
            return response
        version = str(response.get("result") or "0")
        try:
            supported = int(version.split(".", 1)[0]) >= 4
        except ValueError:
            supported = False
        if not supported:
            return _error("API_UNAVAILABLE", "net label replacement requires EasyEDA Pro v4 or newer", editor_version=version)
    prepared = []
    for action in actions:
        replacement = action.get("replacement")
        if replacement:
            point = replacement["at"]
            if error := _validate_grid([point]):
                return error
            existing = by_kind[action["kind"]][action["id"]]
            same = (
                existing.get("net") == replacement.get("net")
                and existing.get("x") == point.get("x")
                and existing.get("y") == point.get("y")
                and existing.get("rotation") == replacement.get("rotation", 0)
                and (action["kind"] != "port" or existing.get("direction_status") != "readback" or existing.get("direction") == replacement.get("direction"))
            )
            if same:
                continue
            desired_exists = any(
                marker_id != action["id"]
                and marker.get("net") == replacement.get("net")
                and marker.get("x") == point.get("x")
                and marker.get("y") == point.get("y")
                and marker.get("rotation") == replacement.get("rotation", 0)
                for marker_id, marker in by_kind[action["kind"]].items()
            )
            if desired_exists:
                prepared.append({"op": "delete", "kind": action["kind"], "id": action["id"]})
                continue
        prepared.append(action)
    if not prepared:
        return {
            "ok": True, "applied": False, "unchanged": True,
            "context_revision": state["context_revision"],
            "revision_before": state["revision"], "revision_after": state["revision"],
        }
    return _checked_write(client, window_id, expected_context_revision, expected_revision, marker_edit_program(prepared))


def set_schematic_no_connects(client, window_id, expected_context_revision, expected_revision, edits):
    for edit in edits:
        if len(edit["pin_selectors"]) != len(set(edit["pin_selectors"])) or any(not re.fullmatch(r"#[A-Za-z0-9_.+/-]+", pin) for pin in edit["pin_selectors"]):
            return _error("INVALID_PIN_SELECTOR", "No Connect selectors must be unique exact #PIN_NUMBER values")
    return _checked_write(client, window_id, expected_context_revision, expected_revision, no_connect_program(edits))
