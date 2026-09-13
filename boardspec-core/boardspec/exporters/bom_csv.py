"""BOM CSV exporter."""

from __future__ import annotations

import csv
import io

from ..core import build_flat

_FIELDNAMES = [
    "reference",
    "logical_path",
    "value",
    "part",
    "footprint",
    "supplier_id",
    "description",
    "dnp",
]


def render_bom_csv(expanded, resolver) -> str:
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
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
