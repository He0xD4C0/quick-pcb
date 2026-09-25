#!/usr/bin/env python3
"""Expand a BoardSpec YAML file: recursively flatten ``kind: module``
definitions into a hierarchical flat instance list and netlist.

Prints ``{ok, errors, warnings, expanded_spec}`` to stdout. The expanded spec
is written to ``--output`` when provided; otherwise ``expanded_spec`` is null.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from ruamel.yaml import YAML

from _bspec import process


def main(argv=None):
    ap = argparse.ArgumentParser(description="Expand a BoardSpec YAML file.")
    ap.add_argument("spec", help="path to the BoardSpec YAML file")
    ap.add_argument("--output", help="write the expanded spec to this file")
    ap.add_argument(
        "--part-db",
        action="append",
        default=[],
        help="additional part database JSON (repeatable; overrides libraries)",
    )
    args = ap.parse_args(argv)

    _, expanded, _, errors, warnings = process(
        os.path.abspath(args.spec), [os.path.abspath(p) for p in args.part_db]
    )
    if errors:
        result = {"ok": False, "errors": errors, "warnings": warnings, "expanded_spec": None}
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            writer = YAML(typ="safe", pure=True)
            writer.version = (1, 2)
            writer.default_flow_style = False
            writer.allow_unicode = True
            writer.dump(expanded, f)
    result = {
        "ok": True,
        "errors": errors,
        "warnings": warnings,
        "expanded_spec": expanded if not args.output else None,
    }
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
