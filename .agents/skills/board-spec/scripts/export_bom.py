#!/usr/bin/env python3
"""Export a bill of materials (CSV) from a BoardSpec YAML file.

Expands modules first, then writes one row per component. Prints
``{ok, errors, warnings}`` to stdout.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

from _bspec import build_flat, process


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export a BOM CSV from a BoardSpec YAML file.")
    ap.add_argument("spec", help="path to the BoardSpec YAML file")
    ap.add_argument("--output", required=True, help="output CSV path")
    ap.add_argument(
        "--part-db",
        action="append",
        default=[],
        help="additional part database JSON (repeatable; overrides libraries)",
    )
    args = ap.parse_args(argv)

    _, expanded, resolver, errors, warnings = process(
        os.path.abspath(args.spec), [os.path.abspath(p) for p in args.part_db]
    )
    if errors:
        json.dump({"ok": False, "errors": errors, "warnings": warnings}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    components, _ = build_flat(expanded, resolver)
    rows = [
        {
            "reference": c["ref"],
            "logical_path": c["logical_path"],
            "value": c["value"],
            "part": c["part"],
            "footprint": c["footprint"],
            "supplier_id": c["supplier_id"],
            "description": c["description"],
            "dnp": "yes" if c["dnp"] else "",
        }
        for c in components
    ]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "reference",
                "logical_path",
                "value",
                "part",
                "footprint",
                "supplier_id",
                "description",
                "dnp",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    json.dump({"ok": True, "errors": errors, "warnings": warnings}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
