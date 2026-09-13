"""Command-line entry points for BoardSpec.

Provides ``boardspec-validate``, ``boardspec-expand``, and ``boardspec-export``
console scripts. Validation prints a single JSON object to stdout and exits
non-zero on errors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .core import process
from .exporters import (
    render_bom_csv,
    render_kicad_netlist,
    render_mermaid,
    render_protel2_netlist,
)
from .yaml_io import dump_yaml

EXPORTERS = {
    "kicad_netlist": render_kicad_netlist,
    "protel2_netlist": render_protel2_netlist,
    "bom_csv": render_bom_csv,
    "mermaid": render_mermaid,
}


def _add_part_db_arg(ap):
    ap.add_argument(
        "--part-db",
        action="append",
        default=[],
        help="additional part database JSON (repeatable; overrides libraries)",
    )


def main_validate(argv=None):
    ap = argparse.ArgumentParser(description="Validate a BoardSpec YAML file.")
    ap.add_argument("spec", help="path to the BoardSpec YAML file")
    _add_part_db_arg(ap)
    args = ap.parse_args(argv)

    _, _, _, errors, warnings = process(
        os.path.abspath(args.spec), [os.path.abspath(p) for p in args.part_db]
    )
    result = {"ok": not errors, "errors": errors, "warnings": warnings}
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if errors else 0


def main_expand(argv=None):
    ap = argparse.ArgumentParser(description="Expand a BoardSpec YAML file.")
    ap.add_argument("spec", help="path to the BoardSpec YAML file")
    ap.add_argument("--output", help="write the expanded spec to this file")
    _add_part_db_arg(ap)
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
            dump_yaml(expanded, f)
    result = {
        "ok": True,
        "errors": errors,
        "warnings": warnings,
        "expanded_spec": expanded if not args.output else None,
    }
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def main_export(argv=None):
    ap = argparse.ArgumentParser(description="Export a BoardSpec YAML file.")
    ap.add_argument("spec", help="path to the BoardSpec YAML file")
    ap.add_argument(
        "target",
        choices=sorted(EXPORTERS),
        help="export format",
    )
    ap.add_argument("--output", help="write output to this file")
    _add_part_db_arg(ap)
    args = ap.parse_args(argv)

    _, expanded, resolver, errors, warnings = process(
        os.path.abspath(args.spec), [os.path.abspath(p) for p in args.part_db]
    )
    if errors:
        json.dump({"ok": False, "errors": errors, "warnings": warnings}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    content = EXPORTERS[args.target](expanded, resolver)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        json.dump(
            {"ok": True, "errors": errors, "warnings": warnings, "output": args.output},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    sys.exit(main_validate())
