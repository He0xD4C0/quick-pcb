"""Deterministic orthogonal routing around schematic component bodies."""

from __future__ import annotations

import math


def _dedupe(points: list[dict]) -> list[dict]:
    result = []
    for point in points:
        value = {"x": point["x"], "y": point["y"]}
        if not result or result[-1] != value:
            result.append(value)
    return result


def _hits_box(a: dict, b: dict, box: dict) -> bool:
    if a["x"] == b["x"]:
        low, high = sorted((a["y"], b["y"]))
        return box["minX"] < a["x"] < box["maxX"] and max(low, box["minY"]) < min(high, box["maxY"])
    if a["y"] == b["y"]:
        low, high = sorted((a["x"], b["x"]))
        return box["minY"] < a["y"] < box["maxY"] and max(low, box["minX"]) < min(high, box["maxX"])
    return True


def _crosses(a: dict, b: dict, c: dict, d: dict) -> bool:
    if a["y"] == b["y"] and c["y"] == d["y"]:
        if a["y"] != c["y"]:
            return False
        return max(min(a["x"], b["x"]), min(c["x"], d["x"])) <= min(max(a["x"], b["x"]), max(c["x"], d["x"]))
    if a["x"] == b["x"] and c["x"] == d["x"]:
        if a["x"] != c["x"]:
            return False
        return max(min(a["y"], b["y"]), min(c["y"], d["y"])) <= min(max(a["y"], b["y"]), max(c["y"], d["y"]))
    vertical_a = a["x"] == b["x"]
    v1, v2, h1, h2 = (a, b, c, d) if vertical_a else (c, d, a, b)
    return (min(h1["x"], h2["x"]) <= v1["x"] <= max(h1["x"], h2["x"])
            and min(v1["y"], v2["y"]) <= h1["y"] <= max(v1["y"], v2["y"]))


def _clear(path: list[dict], boxes: list[dict], occupied: list[tuple[dict, dict]]) -> bool:
    return all(not _hits_box(a, b, box) for a, b in zip(path, path[1:]) for box in boxes) and all(
        not _crosses(a, b, c, d) for a, b in zip(path, path[1:]) for c, d in occupied
    )


def _score(path: list[dict]):
    length = sum(abs(a["x"] - b["x"]) + abs(a["y"] - b["y"]) for a, b in zip(path, path[1:]))
    return length, len(path), [(point["x"], point["y"]) for point in path]


def _snap_below(value: float, grid: float) -> float:
    return math.floor(value / grid) * grid


def _snap_above(value: float, grid: float) -> float:
    return math.ceil(value / grid) * grid


def route_span(start: dict, end: dict, boxes: list[dict], occupied: list[tuple[dict, dict]], grid: float = 10, clearance: float = 100):
    if start["x"] == end["x"] or start["y"] == end["y"]:
        candidates = [[start, end]]
    else:
        candidates = [
            [start, {"x": end["x"], "y": start["y"]}, end],
            [start, {"x": start["x"], "y": end["y"]}, end],
        ]
    for box in boxes:
        for x in (_snap_below(box["minX"] - clearance, grid), _snap_above(box["maxX"] + clearance, grid)):
            candidates.append([start, {"x": x, "y": start["y"]}, {"x": x, "y": end["y"]}, end])
        for y in (_snap_below(box["minY"] - clearance, grid), _snap_above(box["maxY"] + clearance, grid)):
            candidates.append([start, {"x": start["x"], "y": y}, {"x": end["x"], "y": y}, end])
    for a, b in occupied:
        if a["x"] == b["x"]:
            for x in (_snap_below(a["x"] - clearance, grid), _snap_above(a["x"] + clearance, grid)):
                candidates.append([start, {"x": x, "y": start["y"]}, {"x": x, "y": end["y"]}, end])
        else:
            for y in (_snap_below(a["y"] - clearance, grid), _snap_above(a["y"] + clearance, grid)):
                candidates.append([start, {"x": start["x"], "y": y}, {"x": end["x"], "y": y}, end])
    valid = [_dedupe(path) for path in candidates if _clear(_dedupe(path), boxes, occupied)]
    return min(valid, key=_score) if valid else None


def route_orthogonal(points: list[dict], components: list[dict], wires: list[dict] | None = None) -> list[dict] | None:
    boxes = [item["bbox"] for item in components if item.get("bbox")]
    targets = {(point["x"], point["y"]) for point in points}
    boxes.extend(
        {"minX": pin["x"] - 1, "maxX": pin["x"] + 1, "minY": pin["y"] - 1, "maxY": pin["y"] + 1}
        for item in components for pin in item.get("pins", [])
        if pin.get("x") is not None and pin.get("y") is not None and (pin["x"], pin["y"]) not in targets
    )
    occupied = [(a, b) for wire in wires or [] for a, b in zip(wire.get("points", []), wire.get("points", [])[1:])]
    routed = [points[0]]
    for end in points[1:]:
        span = route_span(routed[-1], end, boxes, occupied)
        if not span:
            return None
        routed.extend(span[1:])
    return _dedupe(routed)


def path_is_clear(points: list[dict], components: list[dict], wires: list[dict] | None = None) -> bool:
    """Validate an already-resolved orthogonal path without changing its shape."""
    path = _dedupe(points)
    if len(path) < 2 or any(a["x"] != b["x"] and a["y"] != b["y"] for a, b in zip(path, path[1:])):
        return False
    targets = {(point["x"], point["y"]) for point in path}
    boxes = [item["bbox"] for item in components if item.get("bbox")]
    boxes.extend(
        {"minX": pin["x"] - 1, "maxX": pin["x"] + 1,
         "minY": pin["y"] - 1, "maxY": pin["y"] + 1}
        for item in components for pin in item.get("pins", [])
        if pin.get("x") is not None and pin.get("y") is not None
        and (pin["x"], pin["y"]) not in targets
    )
    occupied = [
        (a, b) for wire in wires or []
        for a, b in zip(wire.get("points", []), wire.get("points", [])[1:])
    ]
    return _clear(path, boxes, occupied)
