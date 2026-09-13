"""Mermaid connectivity diagram exporter (component-level)."""

from __future__ import annotations

from ..core import build_flat

_SAFE = str.maketrans(
    {"<": "&lt;", ">": "&gt;", '"': "&quot;", "\n": " ", "\r": " "}
)


def _s(s):
    return str(s).translate(_SAFE)


def render_mermaid(expanded, resolver) -> str:
    components, nets = build_flat(expanded, resolver)

    # Component-level graph: collapse pins to their owning component.
    refs = sorted({c["ref"] for c in components})
    lines = ["graph LR"]
    for ref in refs:
        lines.append(f"    {_s(ref)}[\"{_s(ref)}\"]")

    edges = set()
    for net in nets:
        involved = sorted({ref for ref, _ in net["nodes"]})
        for i in range(len(involved)):
            for j in range(i + 1, len(involved)):
                a, b = involved[i], involved[j]
                if a == b:
                    continue
                key = tuple(sorted((a, b, net["name"])))
                if key in edges:
                    continue
                edges.add(key)
                lines.append(f"    {_s(a)} ---|{_s(net['name'])}| {_s(b)}")

    return "\n".join(lines) + "\n"
