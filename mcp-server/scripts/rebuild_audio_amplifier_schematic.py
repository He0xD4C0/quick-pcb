#!/usr/bin/env python3
"""Rebuild the authorized S8050/S8550 page as a continuous-wire schematic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from boardspec_mcp.bridge_client import BridgeClient
from boardspec_mcp.schematic_plan import build_plan, diff_plan
from boardspec_mcp.schematic_readability import resolve_plan, verify_readability
from boardspec_mcp.schematic_tools import (
    _state,
    edit_schematic_net_markers,
    get_schematic_violations,
    save_schematic,
    set_schematic_page_format,
    verify_schematic_engineering_drawing,
    verify_schematic_topology,
)
from boardspec_mcp.schematic_writes import (
    create_schematic_wires,
    edit_schematic_wires,
    place_schematic_net_flags,
    place_schematic_net_ports,
    set_schematic_component_placement,
)


PLACEMENTS = {
    "J1": (1000, 1100, 180, False),
    "J2": (1000, 3200, 180, False),
    "C1": (1700, 3200, 180, False),
    "R1": (2400, 3200, 0, False),
    "Q1": (3300, 3200, 180, True),
    "R3": (2900, 4300, 90, False),
    "R4": (3700, 4100, 90, False),
    "C2": (4600, 5000, 90, False),
    "R2": (5000, 5000, 0, False),
    "R5": (4500, 1500, 90, False),
    "D1": (4500, 2300, 90, False),
    "D2": (4500, 3100, 90, False),
    "Q2": (5500, 2200, 180, True),
    "Q3": (5500, 4000, 0, False),
    "R6": (6200, 2600, 90, False),
    "R7": (6200, 3600, 90, False),
    "C3": (7200, 3100, 0, False),
    "C4": (7000, 1500, 90, False),
    "C5": (7700, 1500, 90, False),
    "R8": (7900, 4100, 90, False),
    "C6": (7900, 5000, 90, False),
    "J3": (9000, 3100, 0, False),
}


def require_ok(result: dict, operation: str) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{operation}: {json.dumps(result, ensure_ascii=False)}")
    return result


def live_state(client: BridgeClient, window_id: str) -> dict:
    state, _, error = _state(client, window_id)
    if error:
        require_ok(error, "schematic readback")
    return state


def write_with_readback(
    operation, description: str, *, allow_stale: bool = False
) -> dict:
    result = operation()
    if result.get("code") == "WRITE_STATUS_UNKNOWN":
        print(f"{description}: status unknown; rereading before retry", flush=True)
        return result
    if allow_stale and result.get("code") == "STALE_SCHEMATIC":
        print(f"{description}: revision changed; rereading before retry", flush=True)
        return result
    require_ok(result, description)
    return result


def delete_existing_wiring(client: BridgeClient, window_id: str) -> None:
    while True:
        state = live_state(client, window_id)
        actions = [
            {"op": "delete", "kind": kind, "id": item["id"]}
            for kind, key in (("label", "labels"), ("port", "ports"), ("flag", "flags"))
            for item in state[key]
        ]
        if not actions:
            break
        batch = actions[:8]
        write_with_readback(
            lambda: edit_schematic_net_markers(
                client,
                window_id,
                state["context_revision"],
                state["revision"],
                batch,
                confirm_topology_change=True,
            ),
            "marker deletion",
        )
    while True:
        state = live_state(client, window_id)
        if not state["wires"]:
            break
        actions = [{"op": "delete", "id": item["id"]} for item in state["wires"][:8]]
        write_with_readback(
            lambda: edit_schematic_wires(
                client,
                window_id,
                state["context_revision"],
                state["revision"],
                actions,
            ),
            "wire deletion",
        )


def place_components(client: BridgeClient, window_id: str) -> None:
    for _ in range(20):
        state = live_state(client, window_id)
        current = {item["designator"]: item for item in state["components"]}
        edits = []
        for ref, (x, y, rotation, mirror) in PLACEMENTS.items():
            item = current[ref]
            if (item["x"], item["y"], item["rotation"], item["mirror"]) != (
                x,
                y,
                rotation,
                mirror,
            ):
                edits.append(
                    {
                        "designator": ref,
                        "x": x,
                        "y": y,
                        "rotation": rotation,
                        "mirror": mirror,
                    }
                )
        if not edits:
            return
        batch = edits[:4]
        write_with_readback(
            lambda: set_schematic_component_placement(
                client,
                window_id,
                state["context_revision"],
                state["revision"],
                batch,
            ),
            "component placement",
        )
    raise RuntimeError("component placement did not converge")


def pending_diff(plan: dict, state: dict) -> dict:
    return require_ok(diff_plan(plan, state), "schematic diff")


def apply_plan(client: BridgeClient, window_id: str, plan: dict) -> None:
    for iteration in range(250):
        state = live_state(client, window_id)
        pending = pending_diff(plan, state)
        wiring = pending["wiring"]
        if wiring["wires"]["delete"]:
            actions = [
                {"op": "delete", "id": item["id"]}
                for item in wiring["wires"]["delete"][:4]
            ]
            write_with_readback(
                lambda: edit_schematic_wires(
                    client,
                    window_id,
                    state["context_revision"],
                    state["revision"],
                    actions,
                ),
                "obsolete wire deletion",
                allow_stale=True,
            )
            continue
        if wiring["wires"]["create"]:
            batch = wiring["wires"]["create"][:4]
            write_with_readback(
                lambda: create_schematic_wires(
                    client,
                    window_id,
                    state["context_revision"],
                    state["revision"],
                    batch,
                ),
                "wire creation",
                allow_stale=True,
            )
            print(
                f"wire application pass {iteration + 1}: "
                f"{len(wiring['wires']['create'])} groups pending",
                flush=True,
            )
            continue
        if wiring["ports"]["create"]:
            batch = wiring["ports"]["create"][:2]
            write_with_readback(
                lambda: place_schematic_net_ports(
                    client,
                    window_id,
                    state["context_revision"],
                    state["revision"],
                    batch,
                ),
                "port creation",
                allow_stale=True,
            )
            continue
        if wiring["flags"]["create"]:
            batch = wiring["flags"]["create"][:2]
            write_with_readback(
                lambda: place_schematic_net_flags(
                    client,
                    window_id,
                    state["context_revision"],
                    state["revision"],
                    batch,
                ),
                "flag creation",
                allow_stale=True,
            )
            continue
        marker_deletions = [
            {"op": "delete", "kind": kind[:-1], "id": item["id"]}
            for kind in ("labels", "ports", "flags")
            for item in wiring[kind]["delete"]
        ]
        if marker_deletions:
            write_with_readback(
                lambda: edit_schematic_net_markers(
                    client,
                    window_id,
                    state["context_revision"],
                    state["revision"],
                    marker_deletions[:4],
                    confirm_topology_change=True,
                ),
                "obsolete marker deletion",
                allow_stale=True,
            )
            continue
        if any(wiring[kind]["replace"] for kind in ("labels", "ports", "flags")):
            raise RuntimeError("unexpected marker replacement remained")
        return
    raise RuntimeError("schematic application did not converge")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge-url", default="http://127.0.0.1:49620")
    parser.add_argument("--window-id", required=True)
    parser.add_argument("--project-uuid", required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    client = BridgeClient(args.bridge_url, timeout=45)
    require_ok(client.health(), "bridge readiness")
    before = live_state(client, args.window_id)
    if before["source"].get("project_uuid") != args.project_uuid:
        raise RuntimeError("refusing to operate outside the authorized amplifier project")
    if set(PLACEMENTS) != {item["designator"] for item in before["components"]}:
        raise RuntimeError("the active page is not the expected 22-component amplifier")
    (args.out / "before.json").write_text(
        json.dumps(before, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    delete_existing_wiring(client, args.window_id)
    place_components(client, args.window_id)
    state = live_state(client, args.window_id)
    logical = require_ok(
        build_plan(
            args.spec.read_text(encoding="utf-8"),
            {
                "base_dir": str(args.spec.parent),
                "net_annotation_policy": "sparse_named",
                "preserve_existing_placements": True,
            },
        ),
        "logical planning",
    )["plan"]
    write_with_readback(
        lambda: set_schematic_page_format(
            client,
            args.window_id,
            state["context_revision"],
            state["revision"],
            logical["sheet"],
        ),
        "page format",
    )
    state = live_state(client, args.window_id)
    resolved = require_ok(resolve_plan(logical, state), "continuous route resolution")["plan"]
    (args.out / "resolved-plan.json").write_text(
        json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    apply_plan(client, args.window_id, resolved)

    after = live_state(client, args.window_id)
    final_diff = pending_diff(resolved, after)
    readability = verify_readability(resolved, after)
    topology = verify_schematic_topology(
        client,
        args.spec.read_text(encoding="utf-8"),
        args.window_id,
        str(args.spec.parent),
    )
    drawing = verify_schematic_engineering_drawing(client, resolved, args.window_id)
    drc = get_schematic_violations(client, args.window_id)
    require_ok(readability, "readability verification")
    require_ok(topology, "topology verification")
    require_ok(drawing, "engineering drawing verification")
    require_ok(drc, "strict DRC readback")
    if not drc.get("passed"):
        raise RuntimeError("strict schematic DRC has violations")
    if any(final_diff.get(key) for key in ("create", "move", "conflicts", "extra")):
        raise RuntimeError("component diff is not empty")
    wiring = final_diff["wiring"]
    if any(wiring["wires"][key] for key in ("create", "delete")) or any(
        wiring[kind][key]
        for kind in ("labels", "ports", "flags")
        for key in ("create", "replace", "delete")
    ):
        raise RuntimeError("wiring diff is not empty")

    write_with_readback(
        lambda: save_schematic(
            client,
            args.window_id,
            after["context_revision"],
            after["revision"],
        ),
        "schematic save",
    )
    saved = live_state(client, args.window_id)
    results = {
        "source": saved["source"],
        "revision": saved["revision"],
        "components": len(saved["components"]),
        "nets": len(resolved["topology"]["nets"]),
        "endpoints": sum(len(value) for value in resolved["topology"]["nets"].values()),
        "wires": len(saved["wires"]),
        "ports": len(saved["ports"]),
        "flags": len(saved["flags"]),
        "labels": len(saved["labels"]),
        "named_nets": sum(
            item["net_origin"] == "explicit" for item in resolved["connection_intents"]
        ),
        "anonymous_nets": sum(
            item["net_origin"] == "generated" for item in resolved["connection_intents"]
        ),
        "topology": topology,
        "readability": readability,
        "drawing": drawing,
        "drc": drc,
    }
    (args.out / "result.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
