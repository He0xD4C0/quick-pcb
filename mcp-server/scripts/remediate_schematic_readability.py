#!/usr/bin/env python3
"""Repair marker readability in the authorized disposable schematic project."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from boardspec_mcp.bridge_client import BridgeClient
from boardspec_mcp.schematic_plan import build_plan, diff_plan
from boardspec_mcp.schematic_readability import resolve_plan, verify_readability
from boardspec_mcp.schematic_tools import (
    _state,
    edit_schematic_net_markers,
    get_schematic_context,
    get_schematic_violations,
    open_schematic_page,
    save_schematic,
    verify_schematic_topology,
)
from boardspec_mcp.schematic_writes import (
    create_schematic_wires,
    edit_schematic_wires,
    place_schematic_net_flags,
    place_schematic_net_labels,
    place_schematic_net_ports,
)


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def dump_initial(path: Path, value: object) -> None:
    if not path.exists():
        dump(path, value)


def require_ok(result: dict, operation: str) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{operation} failed: {json.dumps(result, ensure_ascii=False)}")
    return result


def live_state(client: BridgeClient, window_id: str, project_uuid: str, page_uuid: str) -> dict:
    for attempt in range(3):
        state, _, error = _state(client, window_id)
        if not error:
            break
        if error.get("code") not in {"BRIDGE_HTTP_ERROR", "BRIDGE_TIMEOUT"} or attempt == 2:
            require_ok(error, "schematic readback")
        time.sleep(0.5 * (attempt + 1))
    source = state["source"]
    if source.get("project_uuid") != project_uuid or source.get("page_uuid") != page_uuid:
        raise RuntimeError(
            "EDA context drifted: "
            + json.dumps({"expected_project": project_uuid, "expected_page": page_uuid, "actual": source})
        )
    return state


def open_page(client: BridgeClient, window_id: str, project_uuid: str, page_uuid: str) -> None:
    context = require_ok(get_schematic_context(client, window_id), "context read")
    if context["source"].get("project_uuid") != project_uuid:
        raise RuntimeError("refusing to operate outside the authorized disposable project")
    if context["source"].get("page_uuid") != page_uuid:
        require_ok(
            open_schematic_page(
                client, window_id, page_uuid, context["context_revision"],
                confirm_discard_unsaved=True,
            ),
            "page open",
        )
        time.sleep(0.75)
    live_state(client, window_id, project_uuid, page_uuid)


def logical_plan(spec_path: Path) -> dict:
    return require_ok(build_plan(spec_path.read_text(), {
        "base_dir": str(spec_path.parent),
        "high_fanout_primitive": "port",
        "preserve_existing_placements": True,
    }), "logical planning")["plan"]


def endpoint(state: dict, value: object) -> tuple[float, float]:
    if isinstance(value, dict):
        return value["x"], value["y"]
    designator, pin_number = str(value).rsplit(".#", 1)
    component = next(item for item in state["components"] if item["designator"] == designator)
    pin = next(item for item in component["pins"] if str(item["number"]) == pin_number)
    return pin["x"], pin["y"]


def reusable_wire_actions(state: dict, wiring: dict) -> list[dict]:
    extras = {
        frozenset(((item["points"][0]["x"], item["points"][0]["y"]),
                   (item["points"][-1]["x"], item["points"][-1]["y"]))): item
        for item in wiring["wires"]["delete"]
        if item.get("net") is None and len(item.get("points") or []) >= 2
    }
    actions = []
    for wire in wiring["wires"]["create"]:
        for branch in wire["branches"]:
            ends = frozenset((endpoint(state, branch["start"]), endpoint(state, branch["end"])))
            if found := extras.get(ends):
                actions.append({"op": "modify", "id": found["id"], "properties": {"net": wire["net"]}})
    return actions


def reshape_wire_actions(state: dict, wiring: dict) -> list[dict]:
    def on_path(point: tuple[float, float], points: list[tuple[float, float]]) -> bool:
        return any(
            (a[0] == b[0] == point[0] and min(a[1], b[1]) <= point[1] <= max(a[1], b[1]))
            or (a[1] == b[1] == point[1] and min(a[0], b[0]) <= point[0] <= max(a[0], b[0]))
            for a, b in zip(points, points[1:])
        )

    actions, used = [], set()
    for wanted in wiring["wires"]["create"]:
        for branch in wanted["branches"]:
            start = endpoint(state, branch["start"])
            end = endpoint(state, branch["end"])
            for actual in wiring["wires"]["delete"]:
                points = [(item["x"], item["y"]) for item in actual.get("points") or []]
                if (
                    actual["id"] not in used
                    and actual.get("net") == wanted["net"]
                    and on_path(start, points)
                ):
                    path = [
                        {"x": start[0], "y": start[1]},
                        *branch.get("waypoints", []),
                        {"x": end[0], "y": end[1]},
                    ]
                    actions.append({
                        "op": "modify", "id": actual["id"],
                        "properties": {"net": wanted["net"], "points": path},
                    })
                    used.add(actual["id"])
                    break
    return actions


def apply_one_batch(client: BridgeClient, window_id: str, state: dict, diff: dict) -> str | None:
    context, revision = state["context_revision"], state["revision"]
    wiring = diff["wiring"]
    if reshaped := reshape_wire_actions(state, wiring):
        batch = reshaped[:4]
        require_ok(edit_schematic_wires(client, window_id, context, revision, batch), "wire reshaping")
        return f"reshaped {len(batch)} merged wire branches"
    if reusable := reusable_wire_actions(state, wiring):
        batch = reusable[:4]
        require_ok(edit_schematic_wires(client, window_id, context, revision, batch), "wire reuse")
        return f"reused {len(batch)} existing wire branches"
    if wiring["wires"]["delete"]:
        batch = [
            {"op": "delete", "id": item["id"]}
            for item in wiring["wires"]["delete"][:4]
        ]
        require_ok(edit_schematic_wires(client, window_id, context, revision, batch), "obsolete wire deletion")
        return f"deleted {len(batch)} obsolete wires"
    if wiring["wires"]["create"]:
        batch = wiring["wires"]["create"][:4]
        require_ok(create_schematic_wires(client, window_id, context, revision, batch), "wire creation")
        return f"created {len(batch)} wire branches"
    for kind, placer in (
        ("labels", place_schematic_net_labels),
        ("ports", place_schematic_net_ports),
        ("flags", place_schematic_net_flags),
    ):
        if wiring[kind]["create"]:
            batch = wiring[kind]["create"][:4]
            require_ok(placer(client, window_id, context, revision, batch), f"{kind} creation")
            return f"created {len(batch)} {kind}"
    replacements = [
        item for kind in ("labels", "ports", "flags")
        for item in wiring[kind]["replace"]
    ]
    if replacements:
        batch = replacements[:4]
        require_ok(
            edit_schematic_net_markers(client, window_id, context, revision, batch),
            "marker replacement",
        )
        return f"replaced {len(batch)} markers"
    deletions = [
        {"op": "delete", "kind": kind[:-1], "id": item["id"]}
        for kind in ("labels", "ports", "flags")
        for item in wiring[kind]["delete"]
    ]
    if deletions:
        batch = deletions[:4]
        require_ok(
            edit_schematic_net_markers(
                client, window_id, context, revision, batch,
                confirm_topology_change=True,
            ),
            "obsolete marker deletion",
        )
        return f"deleted {len(batch)} obsolete markers"
    return None


def final_diff_empty(diff: dict) -> bool:
    if any(diff.get(key) for key in ("create", "move", "conflicts", "extra")):
        return False
    wiring = diff.get("wiring") or {}
    if any(wiring.get("wires", {}).get(key) for key in ("create", "delete")):
        return False
    if any(wiring.get(kind, {}).get(key) for kind in ("labels", "ports", "flags") for key in ("create", "replace", "delete")):
        return False
    return not any(wiring.get("no_connects", {}).values())


def repair_case(
    client: BridgeClient, window_id: str, project_uuid: str, page_uuid: str,
    spec_path: Path, out: Path, name: str, refresh_plan: bool,
) -> dict:
    open_page(client, window_id, project_uuid, page_uuid)
    before = live_state(client, window_id, project_uuid, page_uuid)
    plan_path = out / f"{name}-resolved-plan.json"
    planning_state = {
        **before,
        "wires": [],
    }
    resolved = (
        require_ok(resolve_plan(logical_plan(spec_path), planning_state), "plan resolution")["plan"]
        if refresh_plan or not plan_path.exists()
        else json.loads(plan_path.read_text())
    )
    initial_diff = require_ok(diff_plan(resolved, before), "initial diff")
    dump_initial(out / f"{name}-before-snapshot.json", before)
    dump(plan_path, resolved)
    dump_initial(out / f"{name}-initial-diff.json", initial_diff)

    operations = []
    for _ in range(100):
        state = live_state(client, window_id, project_uuid, page_uuid)
        pending = require_ok(diff_plan(resolved, state), "incremental diff")
        if pending.get("create") or pending.get("move") or pending.get("conflicts") or pending.get("extra"):
            raise RuntimeError("component placement or identity changed during readability repair")
        operation = apply_one_batch(client, window_id, state, pending)
        if operation is None:
            break
        operations.append(operation)
        print(f"{name}: {operation}", flush=True)
    else:
        raise RuntimeError("readability repair exceeded 100 guarded batches")

    after = live_state(client, window_id, project_uuid, page_uuid)
    final_diff = require_ok(diff_plan(resolved, after), "final diff")
    readability = verify_readability(resolved, after)
    topology = verify_schematic_topology(client, spec_path.read_text(), window_id, str(spec_path.parent))
    drc = get_schematic_violations(client, window_id)
    if not final_diff_empty(final_diff):
        raise RuntimeError("repeat diff is not empty")
    require_ok(readability, "readability verification")
    require_ok(topology, "topology verification")
    require_ok(drc, "DRC readback")
    if not drc.get("passed"):
        raise RuntimeError("strict schematic DRC still has violations")
    require_ok(
        save_schematic(client, window_id, after["context_revision"], after["revision"]),
        "explicit schematic save",
    )
    saved = live_state(client, window_id, project_uuid, page_uuid)
    repeated = require_ok(diff_plan(resolved, saved), "post-save diff")
    if not final_diff_empty(repeated):
        raise RuntimeError("post-save repeat diff is not empty")
    for suffix, value in (
        ("snapshot", saved), ("diff", repeated), ("topology", topology),
        ("drc", drc), ("readability", readability),
    ):
        dump(out / f"{name}-{suffix}.json", value)
    return {
        "page_uuid": page_uuid, "revision": saved["revision"],
        "operations": operations, "topology": topology["counts"],
        "drc_count": drc["total_count"],
        "visible_endpoint_coverage": readability["visible_endpoint_coverage"],
        "repeat_diff_empty": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge-url", default="http://127.0.0.1:49620")
    parser.add_argument("--window-id", required=True)
    parser.add_argument("--project-uuid", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mosfet-page", required=True)
    parser.add_argument("--stc51-page", required=True)
    parser.add_argument("--refresh-plans", action="store_true")
    parser.add_argument("--case", choices=("mosfet-led", "stc51-clock"), action="append")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    client = BridgeClient(args.bridge_url, timeout=45)
    require_ok(client.health(), "Bridge readiness")
    cases = (
        ("mosfet-led", args.mosfet_page, args.repo / "examples/boardspec-e2e-mosfet-led.yaml"),
        ("stc51-clock", args.stc51_page, args.repo / "examples/boardspec-e2e-stc51-clock.yaml"),
    )
    manifest_path = args.out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "format": "schematic-readability-e2e/v0.2", "cases": {},
    }
    manifest.update({"project_uuid": args.project_uuid, "window_id": args.window_id})
    selected = set(args.case or (name for name, _, _ in cases))
    for name, page_uuid, spec_path in cases:
        if name not in selected:
            continue
        manifest["cases"][name] = repair_case(
            client, args.window_id, args.project_uuid, page_uuid,
            spec_path, args.out, name, args.refresh_plans,
        )
    dump(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
