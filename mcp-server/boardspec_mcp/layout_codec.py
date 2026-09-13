"""Deterministic, token-conscious encoding for live EasyEDA PCB layout state."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable

LAYOUT_FORMAT = "layout/easyeda-v0.1"
REVISION_KEYS = (
    "document",
    "layers",
    "stacking",
    "rules",
    "net_classes",
    "differential_pairs",
    "nets",
    "components",
    "lines",
    "arcs",
    "vias",
    "polylines",
    "pours",
    "poured",
    "regions",
    "obstacles",
)


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


def layout_revision(state: dict) -> str:
    """Hash only live, material layout fields and ignore presentation metadata."""
    material = {key: state.get(key) for key in REVISION_KEYS if key in state}
    payload = json.dumps(
        _canonical(material), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def columnar(rows: Iterable[dict], fields: list[str]) -> dict:
    return {
        "fields": fields,
        "rows": [[row.get(field) for field in fields] for row in rows],
    }


def paginate(
    rows: list[dict], cursor: int | None, page_size: int
) -> tuple[list, int | None]:
    start = max(0, int(cursor or 0))
    size = max(1, min(int(page_size), 500))
    end = min(len(rows), start + size)
    return rows[start:end], end if end < len(rows) else None


def bbox_intersects(bbox: dict | None, region: dict | None) -> bool:
    if not region or not bbox:
        return True
    left, right = sorted((region["left"], region["right"]))
    bottom, top = sorted((region["bottom"], region["top"]))
    return not (
        bbox["maxX"] < left
        or bbox["minX"] > right
        or bbox["maxY"] < bottom
        or bbox["minY"] > top
    )


def point_in_region(x: float, y: float, region: dict | None) -> bool:
    if not region:
        return True
    left, right = sorted((region["left"], region["right"]))
    bottom, top = sorted((region["bottom"], region["top"]))
    return left <= x <= right and bottom <= y <= top


def primitive_in_region(item: dict, region: dict | None) -> bool:
    if not region:
        return True
    if item.get("bbox"):
        return bbox_intersects(item["bbox"], region)
    points = []
    for x_key, y_key in (("x", "y"), ("start_x", "start_y"), ("end_x", "end_y")):
        if item.get(x_key) is not None and item.get(y_key) is not None:
            points.append((item[x_key], item[y_key]))
    return any(point_in_region(x, y, region) for x, y in points)


def route_lengths(state: dict) -> dict[str, dict]:
    totals: dict[str, dict] = {}
    for item in state.get("lines", []):
        net = item.get("net") or ""
        length = math.hypot(
            item["end_x"] - item["start_x"], item["end_y"] - item["start_y"]
        )
        bucket = totals.setdefault(net, {"total": 0.0, "by_layer": {}, "vias": 0})
        bucket["total"] += length
        layer = str(item.get("layer"))
        bucket["by_layer"][layer] = bucket["by_layer"].get(layer, 0.0) + length
    for item in state.get("arcs", []):
        net = item.get("net") or ""
        chord = math.hypot(
            item["end_x"] - item["start_x"], item["end_y"] - item["start_y"]
        )
        angle = abs(float(item.get("angle") or 0))
        length = chord
        if angle and angle < 360:
            radians = math.radians(angle)
            length = chord * radians / (2 * math.sin(radians / 2))
        bucket = totals.setdefault(net, {"total": 0.0, "by_layer": {}, "vias": 0})
        bucket["total"] += length
        layer = str(item.get("layer"))
        bucket["by_layer"][layer] = bucket["by_layer"].get(layer, 0.0) + length
    for item in state.get("vias", []):
        net = item.get("net") or ""
        totals.setdefault(net, {"total": 0.0, "by_layer": {}, "vias": 0})["vias"] += 1
    return totals


def component_overlaps(components: list[dict]) -> list[list[str]]:
    overlaps: list[list[str]] = []
    ordered = [item for item in components if item.get("bbox")]
    for index, left in enumerate(ordered):
        a = left["bbox"]
        for right in ordered[index + 1 :]:
            b = right["bbox"]
            if not (
                a["maxX"] <= b["minX"]
                or a["minX"] >= b["maxX"]
                or a["maxY"] <= b["minY"]
                or a["minY"] >= b["maxY"]
            ):
                overlaps.append([left.get("designator"), right.get("designator")])
    return overlaps


def bbox_union_area(boxes: Iterable[dict]) -> float:
    """Return the exact union area of axis-aligned bounding boxes."""
    boxes = [box for box in boxes if box]
    xs = sorted({value for box in boxes for value in (box["minX"], box["maxX"])})
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        if right <= left:
            continue
        intervals = sorted(
            (box["minY"], box["maxY"])
            for box in boxes
            if box["minX"] < right and box["maxX"] > left
        )
        covered = 0.0
        if intervals:
            start, end = intervals[0]
            for low, high in intervals[1:]:
                if low > end:
                    covered += max(0.0, end - start)
                    start, end = low, high
                else:
                    end = max(end, high)
            covered += max(0.0, end - start)
        area += (right - left) * covered
    return area


def layer_dictionary(state: dict) -> dict:
    return columnar(
        sorted(state.get("layers", []), key=lambda item: item.get("id", 0)),
        ["id", "name", "type"],
    )


def net_dictionary(state: dict) -> tuple[list[str], dict[str, int]]:
    values = sorted(
        {
            str(item.get("net"))
            for item in state.get("nets", [])
            if item.get("net") is not None
        }
    )
    return values, {value: index for index, value in enumerate(values)}


def base_response(state: dict, scope: dict | None = None) -> dict:
    return {
        "format": LAYOUT_FORMAT,
        "source": "easyeda-pro-live",
        "unit": "mil",
        "range": scope or {"kind": "all"},
        "document": state.get("document"),
        "revision": layout_revision(state),
    }
