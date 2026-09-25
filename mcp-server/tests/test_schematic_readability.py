"""Tests for resolved schematic connection readability."""

from __future__ import annotations

import copy

from boardspec_mcp import schematic_tools
from boardspec_mcp.schematic_codec import normalize_state
from boardspec_mcp.schematic_plan import diff_plan
from boardspec_mcp.schematic_readability import resolve_plan, verify_readability


def _component(designator="U1", bbox=None, pins=None):
    return {
        "id": f"component-{designator.lower()}", "designator": designator,
        "name": designator, "component": {"libraryUuid": "lib", "uuid": "dev"},
        "x": 1000, "y": 1000, "rotation": 0, "mirror": False,
        "bbox": bbox or {"minX": 900, "minY": 900, "maxX": 1100, "maxY": 1100},
        "pins": pins or [],
    }


def _state(components=None, wires=None, ports=None):
    return {
        "source": {
            "project_uuid": "project", "schematic_uuid": "schematic",
            "page_uuid": "page", "document_uuid": "page", "document_type": 1,
            "tab_id": "tab",
        },
        "components": components or [], "wires": wires or [], "labels": [],
        "ports": ports or [], "flags": [], "no_connects": [], "nets": [],
        "netlist": "PROTEL NETLIST 2.0\n[\nU1\n\n]\n",
    }


def _plan(intents):
    return {
        "format": "schematic-plan/v0.2", "phase": "logical",
        "options": {
            "page_policy": "single_page", "wiring_policy": "hybrid",
            "grid_mil": 100, "column_gap_mil": 1000, "row_gap_mil": 600,
            "group_by_module": True, "high_fanout_primitive": "auto",
            "readability_policy": "standard_hybrid",
            "stub_lengths_mil": [200, 300, 400, 500, 600],
            "marker_clearance_mil": 100, "use_trusted_pin_directions": True,
            "cross_region_distance_mil": 2000,
            "preserve_existing_placements": False,
            "measured_geometry": {},
        },
        "placements": [], "wires": [], "labels": [], "ports": [], "flags": [],
        "no_connects": [], "connection_intents": intents,
        "topology": {"components": ["U1"], "nets": {}},
        "topology_hash": "sha256:topology", "plan_hash": "sha256:logical",
    }


def test_resolver_orients_each_side_and_uses_only_trusted_directions():
    pins = [
        {"number": "1", "x": 900, "y": 1000, "rotation": 0},
        {"number": "2", "x": 1100, "y": 1000, "rotation": 180},
        {"number": "3", "x": 1000, "y": 900, "rotation": 90},
        {"number": "4", "x": 1000, "y": 1100, "rotation": 270},
    ]
    intents = []
    types = [("input", True), ("output", True), ("tri_state", True), ("output", False)]
    for index, (pin_type, trusted) in enumerate(types, 1):
        intents.append({
            "net": f"N{index}", "strategy": "port",
            "endpoints": [{
                "selector": f"U1.#{index}", "region": "root",
                "pin_type": pin_type, "pin_type_trusted": trusted,
            }],
        })
    result = resolve_plan(_plan(intents), _state([_component(pins=pins)]))
    assert result["ok"] is True
    ports = {item["anchor"]: item for item in result["plan"]["ports"]}
    assert [ports[f"U1.#{index}"]["rotation"] for index in range(1, 5)] == [180, 0, 270, 90]
    assert [ports[f"U1.#{index}"]["direction"] for index in range(1, 5)] == ["IN", "OUT", "OUT", "BI"]
    assert all(branch["role"] == "stub" for wire in result["plan"]["wires"] for branch in wire["branches"])


def test_resolver_uses_local_lane_without_rotating_a_blocked_marker():
    u1 = _component(pins=[{"number": "1", "x": 900, "y": 1000, "rotation": 0}])
    blocker = _component("X1", {"minX": 300, "minY": 800, "maxX": 800, "maxY": 1200})
    intent = [{
        "net": "BLOCKED", "strategy": "port",
        "endpoints": [{"selector": "U1.#1", "region": "root", "pin_type_trusted": False}],
    }]
    result = resolve_plan(_plan(intent), _state([u1, blocker]))
    assert result["ok"] is True
    assert result["plan"]["visual"]["fallbacks"] == [
        {"net": "BLOCKED", "anchor": "U1.#1", "to": "local_lane", "side": "left"}
    ]
    assert result["plan"]["wires"][0]["branches"][0]["role"] == "stub"


def test_readability_requires_stub_and_rejects_actual_marker_overlap():
    component = _component(pins=[{"number": "1", "x": 900, "y": 1000, "rotation": 0}])
    intent = [{
        "net": "SIG", "strategy": "port",
        "endpoints": [{"selector": "U1.#1", "region": "root", "pin_type_trusted": False}],
    }]
    resolved = resolve_plan(_plan(intent), _state([component]))["plan"]
    marker = resolved["ports"][0]
    point = marker["at"]
    live = _state(
        [component],
        wires=[{"id": "wire", "net": "SIG", "points": [{"x": 900, "y": 1000}, point]}],
        ports=[{
            "id": "port", "net": "SIG", "x": point["x"], "y": point["y"],
            "rotation": 180, "direction": "BI", "direction_status": "readback",
            "bbox": {"minX": 850, "minY": 950, "maxX": 1050, "maxY": 1050},
        }],
    )
    result = verify_readability(resolved, live)
    assert result["passed"] is False
    assert {item["code"] for item in result["issues"]} == {"MARKER_COMPONENT_OVERLAP"}


def test_diff_emits_marker_replace_and_then_becomes_unchanged():
    component = _component(pins=[{"number": "1", "x": 900, "y": 1000, "rotation": 0}])
    intent = [{
        "net": "SIG", "strategy": "port",
        "endpoints": [{"selector": "U1.#1", "region": "root", "pin_type_trusted": False}],
    }]
    resolved = resolve_plan(_plan(intent), _state([component]))["plan"]
    old = {"id": "old", "net": "SIG", "x": 900, "y": 1000, "rotation": 0}
    first = diff_plan(resolved, normalize_state(_state([component], ports=[old]), "window"))
    assert first["wiring"]["ports"]["replace"][0]["id"] == "old"
    wanted = resolved["ports"][0]
    current = {
        "id": "new", "net": "SIG", "x": wanted["at"]["x"], "y": wanted["at"]["y"],
        "rotation": wanted["rotation"],
    }
    second = diff_plan(resolved, normalize_state(_state([component], ports=[current]), "window"))
    assert second["wiring"]["ports"]["replace"] == []
    assert second["wiring"]["ports"]["unchanged"] == ["new"]


def test_diff_reserves_exact_marker_matches_before_nearest_replacements():
    plan = _plan([{
        "net": "GND", "kind": "ground", "strategy": "flag", "endpoints": [],
    }])
    plan.update({
        "phase": "resolved",
        "flags": [
            {"client_id": "a", "net": "GND", "at": {"x": 0, "y": 0},
             "rotation": 0, "identification": "Ground", "anchor": "U1.#1"},
            {"client_id": "b", "net": "GND", "at": {"x": 100, "y": 0},
             "rotation": 0, "identification": "Ground", "anchor": "U1.#2"},
        ],
    })
    state = normalize_state(_state([_component()]), "window")
    state["components"] = []
    state["flags"] = [
        {"id": "near-first", "net": "GND", "x": 50, "y": 0, "rotation": 0,
         "identification_status": "unsupported"},
        {"id": "exact-second", "net": "GND", "x": 100, "y": 0, "rotation": 0,
         "identification_status": "unsupported"},
    ]
    result = diff_plan(plan, state)["wiring"]["flags"]
    assert result["create"] == []
    assert result["unchanged"] == ["exact-second"]
    assert result["replace"][0]["id"] == "near-first"


def test_existing_reversed_wire_is_oriented_to_the_planned_start():
    left = _component("U1", pins=[{"number": "1", "x": 1100, "y": 1000, "rotation": 180}])
    right = _component(
        "R1", {"minX": 1900, "minY": 900, "maxX": 2100, "maxY": 1100},
        [{"number": "1", "x": 1900, "y": 1000, "rotation": 0}],
    )
    intent = [{
        "net": "DIRECT", "strategy": "direct",
        "endpoints": [
            {"selector": "U1.#1", "region": "root", "pin_type_trusted": False},
            {"selector": "R1.#1", "region": "root", "pin_type_trusted": False},
        ],
    }]
    existing = [{
        "id": "wire", "net": "DIRECT",
        "points": [{"x": 1900, "y": 1000}, {"x": 1500, "y": 1000}, {"x": 1100, "y": 1000}],
    }]
    result = resolve_plan(_plan(intent), _state([left, right], wires=existing))
    branch = result["plan"]["wires"][0]["branches"][0]
    path = [{"x": 1100, "y": 1000}, *branch["waypoints"], {"x": 1900, "y": 1000}]
    assert all(a["x"] == b["x"] or a["y"] == b["y"] for a, b in zip(path, path[1:]))


def test_resolver_uses_ports_for_spatially_cross_region_two_pin_net():
    left = _component("U1", pins=[{"number": "1", "x": 1100, "y": 1000, "rotation": 180}])
    right = _component(
        "J1", {"minX": 3900, "minY": 900, "maxX": 4100, "maxY": 1100},
        [{"number": "1", "x": 3900, "y": 1000, "rotation": 0}],
    )
    intent = [{
        "net": "REMOTE", "strategy": "direct",
        "endpoints": [
            {"selector": "U1.#1", "region": "root", "pin_type_trusted": False},
            {"selector": "J1.#1", "region": "root", "pin_type_trusted": False},
        ],
    }]
    result = resolve_plan(_plan(intent), _state([left, right]))
    assert result["ok"] is True
    assert len(result["plan"]["ports"]) == 2
    assert result["plan"]["visual"]["fallbacks"][0]["reason"] == "spatially_cross_region"


def test_resolver_can_freeze_live_component_positions():
    component = _component(pins=[{"number": "1", "x": 900, "y": 1000, "rotation": 0}])
    plan = _plan([{
        "net": "SIG", "strategy": "port",
        "endpoints": [{"selector": "U1.#1", "region": "root", "pin_type_trusted": False}],
    }])
    plan["options"]["preserve_existing_placements"] = True
    plan["placements"] = [{
        "client_id": "plan/U1", "logical_path": "U1", "library_uuid": "lib",
        "device_uuid": "dev", "device_name": None, "designator": "U1",
        "x": 100, "y": 100, "rotation": 90, "mirror": True,
    }]
    result = resolve_plan(plan, _state([component]))
    assert result["ok"] is True
    placement = result["plan"]["placements"][0]
    assert (
        placement["x"], placement["y"], placement["rotation"], placement["mirror"]
    ) == (1000, 1000, 0, False)


class _FakeClient:
    def __init__(self, before, after):
        self.before, self.after = before, after
        self.mutated, self.calls = False, []

    def health(self):
        return {"ok": True, "active_window_id": "window"}

    def list_windows(self):
        return {"ok": True, "windows": [{"id": "window"}]}

    def execute(self, code, window_id=None):
        self.calls.append(code)
        if "const componentRaw" in code:
            return {"ok": True, "result": copy.deepcopy(self.after if self.mutated else self.before)}
        if "sch_Drc.check" in code:
            return {"ok": True, "result": []}
        if "getEditorCurrentVersion" in code:
            return {"ok": True, "result": "3.2.186"}
        self.mutated = True
        return {"ok": True, "result": [{"ok": True, "op": "replace", "id": "old", "new_id": "new"}]}


def test_marker_replacement_is_checked_and_pure_delete_requires_confirmation():
    component = _component()
    old = {"id": "old", "net": "SIG", "x": 900, "y": 1000, "rotation": 0}
    new = {"id": "new", "net": "SIG", "x": 700, "y": 1000, "rotation": 180}
    before, after = _state([component], ports=[old]), _state([component], ports=[new])
    normalized = normalize_state(before, "window")
    action = [{
        "op": "replace", "kind": "port", "id": "old",
        "replacement": {
            "kind": "port", "client_id": "plan/SIG/port/0", "net": "SIG",
            "at": {"x": 700, "y": 1000}, "rotation": 180, "mirror": False,
            "direction": "BI", "anchor": "U1.#1", "side": "left",
        },
    }]
    result = schematic_tools.edit_schematic_net_markers(
        _FakeClient(before, after), "window", normalized["context_revision"], normalized["revision"], action
    )
    assert result["ok"] is True
    refused = schematic_tools.edit_schematic_net_markers(
        _FakeClient(before, before), "window", normalized["context_revision"], normalized["revision"],
        [{"op": "delete", "kind": "port", "id": "old"}],
    )
    assert refused["code"] == "CONFIRMATION_REQUIRED"
