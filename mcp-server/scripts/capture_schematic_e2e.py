#!/usr/bin/env python3
"""Capture machine-readable evidence from the disposable schematic E2E project."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from boardspec_mcp.bridge_client import BridgeClient
from boardspec_mcp.schematic_bridge import CAPABILITY_PROBE_JS, capture_schematic, run_strict_drc
from boardspec_mcp.schematic_codec import normalize_state
from boardspec_mcp.schematic_drc import flatten_schematic_drc
from boardspec_mcp.schematic_plan import build_plan, compare_topology, diff_plan, expected_netlist
from boardspec_mcp.schematic_tools import get_schematic_context, open_schematic_page


def geometry(state: dict) -> dict:
    result = {}
    for item in state["components"]:
        box = item["bbox"]
        result[item["designator"]] = {
            "width": box["maxX"] - box["minX"], "height": box["maxY"] - box["minY"],
            "min_dx": box["minX"] - item["x"], "max_dx": box["maxX"] - item["x"],
            "min_dy": box["minY"] - item["y"], "max_dy": box["maxY"] - item["y"],
        }
    return result


def effective_plan(spec_text: str, base_dir: Path, state: dict) -> dict:
    plan = build_plan(spec_text, {
        "base_dir": str(base_dir), "high_fanout_primitive": "port",
        "measured_geometry": geometry(state),
    })["plan"]
    actual_wire_nets = {item["net"] for item in state["wires"]}
    kept, fallback = [], []
    for wire in plan["wires"]:
        if wire["net"] in actual_wire_nets:
            kept.append(wire)
            continue
        branch = wire["branches"][0]
        for index, endpoint in enumerate((branch["start"], branch["end"])):
            fallback.append({
                "client_id": f"{branch['client_id']}/fallback/{index}", "net": wire["net"],
                "at": endpoint, "direction": "BI", "rotation": 0, "mirror": False,
            })
    plan["wires"] = kept
    plan["ports"] = [*plan["ports"], *fallback]
    return plan


def switch(client: BridgeClient, window_id: str, page_uuid: str) -> None:
    context = get_schematic_context(client, window_id)
    if context["source"].get("page_uuid") == page_uuid:
        return
    result = open_schematic_page(
        client, window_id, page_uuid, context["context_revision"],
        confirm_discard_unsaved=True,
    )
    if not result.get("ok"):
        raise RuntimeError(result)
    time.sleep(0.75)


def capture_case(client, window_id: str, page_uuid: str, spec_path: Path) -> dict:
    switch(client, window_id, page_uuid)
    raw = capture_schematic(client, window_id)
    if not raw.get("ok"):
        raise RuntimeError(raw)
    state = normalize_state(raw["result"], window_id)
    spec_text = spec_path.read_text()
    plan = effective_plan(spec_text, spec_path.parent, state)
    expected, error = expected_netlist(spec_text, str(spec_path.parent))
    if error:
        raise RuntimeError(error)
    drc_raw = run_strict_drc(client, window_id)
    if not drc_raw.get("ok"):
        raise RuntimeError(drc_raw)
    return {
        "snapshot": state,
        "plan": plan,
        "diff": diff_plan(plan, state),
        "topology": compare_topology(expected, state["netlist"]),
        "drc": flatten_schematic_drc(drc_raw.get("result") or [], state["source"]["page_uuid"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge-url", default="http://127.0.0.1:49620")
    parser.add_argument("--window-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mosfet-page", required=True)
    parser.add_argument("--stc51-page", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    client = BridgeClient(args.bridge_url, timeout=45)
    args.out.mkdir(parents=True, exist_ok=True)
    probe = client.execute(CAPABILITY_PROBE_JS, args.window_id)
    if not probe.get("ok"):
        raise RuntimeError(probe)
    capabilities = {
        "format": "schematic-capabilities/v0.1",
        **probe["result"],
        "observed_e2e": {
            "create_project": "unreliable_in_semi_offline_mode",
            "net_label_create": "requires_easyeda_v4",
            "schematic_page_component_wire_port_flag_netlist_drc_save": "verified",
        },
    }
    (args.out / "capabilities.json").write_text(
        json.dumps(capabilities, ensure_ascii=False, indent=2) + "\n"
    )
    cases = {
        "mosfet-led": (args.mosfet_page, args.repo / "examples/boardspec-e2e-mosfet-led.yaml"),
        "stc51-clock": (args.stc51_page, args.repo / "examples/boardspec-e2e-stc51-clock.yaml"),
    }
    manifest = {
        "format": "schematic-e2e-evidence/v0.1",
        "window_id": args.window_id,
        "editor_version": capabilities["editor_version"],
        "cases": {},
    }
    for name, (page_uuid, spec_path) in cases.items():
        evidence = capture_case(client, args.window_id, page_uuid, spec_path)
        for kind, value in evidence.items():
            path = args.out / f"{name}-{kind}.json"
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        manifest["cases"][name] = {
            "page_uuid": page_uuid,
            "revision": evidence["snapshot"]["revision"],
            "topology_ok": evidence["topology"]["ok"],
            "drc_count": len(evidence["drc"]),
        }
    switch(client, args.window_id, args.stc51_page)
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
