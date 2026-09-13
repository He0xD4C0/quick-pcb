#!/usr/bin/env python3
"""Export a legacy KiCad Eeschema S-expression netlist from a BoardSpec YAML file.

Expands modules first, then emits a ``(export ...)`` netlist with one
``(comp ...)`` per component and one ``(net ...)`` per net. This is an exchange
file, not a ``.kicad_sch`` project.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from _bspec import build_flat, process

_REF_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def _quote(value):
    return '"' + str(value).replace('"', '\\"') + '"'


def _comp_ref_key(ref):
    """Sort key so U1 < U2 < ... < U10, LED1 < LED2, etc."""
    m = _REF_RE.match(ref)
    if m:
        return (m.group(1), int(m.group(2)), ref)
    return (ref, 0, ref)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Export a KiCad netlist from a BoardSpec YAML file."
    )
    ap.add_argument("spec", help="path to the BoardSpec YAML file")
    ap.add_argument("--output", required=True, help="output .net path")
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

    components, nets = build_flat(expanded, resolver)
    components = sorted(components, key=lambda c: _comp_ref_key(c["ref"]))

    lines = ["(export (version D)"]
    lines.append("  (components")
    for c in components:
        lines.append(f"    (comp (ref {_quote(c['ref'])})")
        if c["value"]:
            lines.append(f"      (value {_quote(c['value'])})")
        if c["footprint"]:
            lines.append(f"      (footprint {_quote(c['footprint'])})")
        lines.append("    )")
    lines.append("  )")
    lines.append("  (nets")
    for net in nets:
        lines.append(f"    (net (code {_quote('')}) (name {_quote(net['name'])})")
        for ref, pin in net["nodes"]:
            lines.append(f"      (node (ref {_quote(ref)}) (pin {_quote(pin)}))")
        lines.append("    )")
    lines.append("  )")
    lines.append(")")

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    json.dump({"ok": True, "errors": errors, "warnings": warnings}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
