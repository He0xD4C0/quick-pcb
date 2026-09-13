#!/usr/bin/env python3
"""Compare a BoardSpec graph with the active EasyEDA Pro PCB Protel2 netlist."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from boardspec import process
from boardspec.exporters.netlist_protel2 import (
    parse_protel2_netlist,
    render_protel2_netlist,
)
from boardspec_mcp.bridge_client import BridgeClient
from boardspec_mcp.tools import get_netlist


def _net_diff(expected: dict, actual: dict) -> dict:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = {}
    for name in sorted(set(expected) & set(actual)):
        expected_nodes = {tuple(node) for node in expected[name]}
        actual_nodes = {tuple(node) for node in actual[name]}
        if expected_nodes != actual_nodes:
            changed[name] = {
                "missing_nodes": sorted(expected_nodes - actual_nodes),
                "extra_nodes": sorted(actual_nodes - expected_nodes),
            }
    return {"missing": missing, "extra": extra, "changed": changed}


def compare(expected: dict, actual: dict) -> dict:
    expected_refs = set(expected["components"])
    actual_refs = set(actual["components"])
    net_diff = _net_diff(expected["nets"], actual["nets"])
    missing_refs = sorted(expected_refs - actual_refs)
    extra_refs = sorted(actual_refs - expected_refs)
    passed = not missing_refs and not extra_refs and not any(net_diff.values())
    return {
        "passed": passed,
        "summary": {
            "expected_components": len(expected_refs),
            "actual_components": len(actual_refs),
            "expected_nets": len(expected["nets"]),
            "actual_nets": len(actual["nets"]),
            "expected_nodes": sum(len(nodes) for nodes in expected["nets"].values()),
            "actual_nodes": sum(len(nodes) for nodes in actual["nets"].values()),
        },
        "components": {"missing": missing_refs, "extra": extra_refs},
        "nets": net_diff,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--bridge-url",
        default=os.environ.get("BOARDSPEC_BRIDGE_URL", ""),
        help="EasyEDA bridge base URL; otherwise scan ports 49620-49629",
    )
    args = parser.parse_args()

    _, expanded, resolver, errors, warnings = process(str(args.spec))
    if errors:
        print(json.dumps({"passed": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 2

    expected_text = render_protel2_netlist(expanded, resolver)
    response = get_netlist(
        BridgeClient(base_url=args.bridge_url or None, timeout=30),
        "PROTEL2",
        "pcb",
    )
    if not response.get("ok"):
        print(json.dumps({"passed": False, "bridge": response}, ensure_ascii=False, indent=2))
        return 3

    actual_text = response.get("result")
    if not isinstance(actual_text, str):
        print(json.dumps({"passed": False, "error": "EDA returned a non-text netlist"}, indent=2))
        return 4

    expected = parse_protel2_netlist(expected_text)
    actual = parse_protel2_netlist(actual_text)
    report = compare(expected, actual)
    report.update(
        {
            "spec": str(args.spec.resolve()),
            "reference_map": expanded.get("reference_map", {}),
            "warnings": warnings,
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "boardspec-expected.net").write_text(expected_text, encoding="utf-8")
    (args.output_dir / "eda-readback.net").write_text(actual_text, encoding="utf-8")
    (args.output_dir / "roundtrip-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
