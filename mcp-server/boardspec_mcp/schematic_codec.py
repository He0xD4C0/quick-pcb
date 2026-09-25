"""Canonical encoding, units and revisions for EasyEDA schematic state."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

SCHEMATIC_FORMAT = "schematic/easyeda-v0.1"
EDA_UNIT_MIL = 10
MATERIAL_KEYS = (
    "components",
    "wires",
    "labels",
    "ports",
    "flags",
    "no_connects",
)


def natural_key(value: object):
    return tuple(
        int(token) if token.isdigit() else token.lower()
        for token in re.split(r"(\d+)", str(value or ""))
    )


def require_grid(value: float, grid_mil: int = 10) -> float:
    number = float(value)
    if abs(number / grid_mil - round(number / grid_mil)) > 1e-9:
        raise ValueError(f"coordinate {value} is not on the {grid_mil} mil grid")
    return number


def to_eda(value: float) -> float:
    return require_grid(value) / EDA_UNIT_MIL


def from_eda(value: float | int | None):
    return None if value is None else float(value) * EDA_UNIT_MIL


def _canonical(value):
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [_canonical(item) for item in value]
        return sorted(
            items,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, float) and value == 0:
        return 0.0
    return value


def _digest(value: object) -> str:
    payload = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def context_revision(source: dict) -> str:
    keys = (
        "window_id",
        "project_uuid",
        "schematic_uuid",
        "page_uuid",
        "document_uuid",
        "tab_id",
    )
    return _digest({key: source.get(key) for key in keys})


def schematic_revision(state: dict) -> str:
    return _digest({key: state.get(key, []) for key in MATERIAL_KEYS})


def canonical_points(points: list[dict]) -> list[dict]:
    clean = [{"x": float(p["x"]), "y": float(p["y"])} for p in points]
    if len(clean) > 1:
        reverse = list(reversed(clean))
        if json.dumps(reverse, sort_keys=True) < json.dumps(clean, sort_keys=True):
            clean = reverse
    return clean


def primitive_in_region(item: dict, region: dict | None) -> bool:
    """Return whether a schematic primitive intersects an inclusive mil region."""
    if not region:
        return True
    left, right = sorted((region["left"], region["right"]))
    bottom, top = sorted((region["bottom"], region["top"]))

    box = item.get("bbox")
    if box:
        return not (
            box["maxX"] < left
            or box["minX"] > right
            or box["maxY"] < bottom
            or box["minY"] > top
        )

    points = item.get("points") or []
    if points:
        return any(
            not (
                max(a["x"], b["x"]) < left
                or min(a["x"], b["x"]) > right
                or max(a["y"], b["y"]) < bottom
                or min(a["y"], b["y"]) > top
            )
            for a, b in zip(points, points[1:])
        ) or (
            len(points) == 1
            and left <= points[0]["x"] <= right
            and bottom <= points[0]["y"] <= top
        )

    point = item.get("position") or item
    x, y = point.get("x"), point.get("y")
    return x is not None and y is not None and left <= x <= right and bottom <= y <= top


def normalize_state(raw: dict, window_id: str) -> dict:
    state = dict(raw)
    source = dict(state.get("source") or {})
    source["window_id"] = window_id
    state["source"] = source
    for component in state.get("components", []):
        component["pins"] = sorted(
            component.get("pins", []), key=lambda p: natural_key(p.get("number"))
        )
    for wire in state.get("wires", []):
        wire["points"] = canonical_points(wire.get("points") or [])
    state["components"] = sorted(
        state.get("components", []),
        key=lambda row: (natural_key(row.get("designator")), row.get("id") or ""),
    )
    for key in ("wires", "labels", "ports", "flags", "no_connects"):
        state[key] = sorted(
            state.get(key, []),
            key=lambda row: json.dumps(_canonical(row), sort_keys=True),
        )
    state["format"] = SCHEMATIC_FORMAT
    state["unit"] = "mil"
    state["context_revision"] = context_revision(source)
    state["revision"] = schematic_revision(state)
    return state


def columnar(rows: Iterable[dict], fields: list[str]) -> dict:
    return {"fields": fields, "rows": [[row.get(field) for field in fields] for row in rows]}


def paginate(rows: list[dict], cursor: int | None, page_size: int):
    start = max(0, int(cursor or 0))
    size = max(1, min(500, int(page_size)))
    end = min(len(rows), start + size)
    return rows[start:end], end if end < len(rows) else None
