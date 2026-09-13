"""Legacy KiCad Eeschema S-expression netlist exporter.

Emits a ``(export ...)`` netlist exchange file (not a ``.kicad_sch`` project).
"""

from __future__ import annotations

import re

from ..core import build_flat

_REF_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def _quote(value):
    return '"' + str(value).replace('"', '\\"') + '"'


def _ref_key(ref):
    m = _REF_RE.match(ref)
    if m:
        return (m.group(1), int(m.group(2)), ref)
    return (ref, 0, ref)


def render_kicad_netlist(expanded, resolver) -> str:
    components, nets = build_flat(expanded, resolver)
    components = sorted(components, key=lambda c: _ref_key(c["ref"]))

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
    return "\n".join(lines) + "\n"
