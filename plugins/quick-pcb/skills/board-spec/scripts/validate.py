#!/usr/bin/env python3
"""Validate a BoardSpec YAML file.

Prints a single JSON object ``{ok, errors, warnings}`` to stdout and exits
non-zero when there are errors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from _bspec import process


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate a BoardSpec YAML file.")
    ap.add_argument("spec", help="path to the BoardSpec YAML file")
    ap.add_argument(
        "--part-db",
        action="append",
        default=[],
        help="additional part database JSON (repeatable; overrides libraries)",
    )
    args = ap.parse_args(argv)

    _, _, _, errors, warnings = process(
        os.path.abspath(args.spec), [os.path.abspath(p) for p in args.part_db]
    )
    result = {"ok": not errors, "errors": errors, "warnings": warnings}
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
