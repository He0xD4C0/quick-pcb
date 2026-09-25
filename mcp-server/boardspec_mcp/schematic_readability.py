"""Resolve and verify human-readable schematic connections."""

from __future__ import annotations

import copy
import heapq
import hashlib
import json
import re
from .schematic_codec import natural_key, require_grid
from .schematic_routing import route_orthogonal

PIN_SELECTOR = re.compile(r"^(.+)\.#([^#]+)$")
SIDES = ("left", "right", "top", "bottom")
VECTORS = {
    "left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1),
}
ROTATIONS = {"left": 180, "right": 0, "top": 270, "bottom": 90}

def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

def _error(code: str, message: str, **extra) -> dict:
    return {"ok": False, "code": code, "message": message, **extra}


def _pin_index(state: dict) -> dict[str, tuple[dict, dict]]:
    return {
        f"{component.get('designator')}.#{pin.get('number')}": (component, pin)
        for component in state.get("components", [])
        for pin in component.get("pins", [])
    }


def _side(component: dict, pin: dict) -> str:
    box = component.get("bbox") or {}
    if not all(key in box for key in ("minX", "maxX", "minY", "maxY")):
        rotation_side = {0: "left", 180: "right", 90: "top", 270: "bottom"}
        return rotation_side.get(int(pin.get("rotation") or 0) % 360, "right")
    outside = {
        "left": max(0, box["minX"] - pin["x"]),
        "right": max(0, pin["x"] - box["maxX"]),
        "top": max(0, box["minY"] - pin["y"]),
        "bottom": max(0, pin["y"] - box["maxY"]),
    }
    if max(outside.values()) > 0:
        best = max(outside.values())
        tied = [name for name in SIDES if outside[name] == best]
        return tied[0]
    distances = {
        "left": abs(pin["x"] - box["minX"]),
        "right": abs(pin["x"] - box["maxX"]),
        "top": abs(pin["y"] - box["minY"]),
        "bottom": abs(pin["y"] - box["maxY"]),
    }
    best = min(distances.values())
    tied = [name for name in SIDES if distances[name] == best]
    rotation_side = {0: "left", 180: "right", 90: "top", 270: "bottom"}.get(
        int(pin.get("rotation") or 0) % 360
    )
    return rotation_side if rotation_side in tied else tied[0]


def _direction(pin_type: str | None, trusted: bool, enabled: bool) -> str:
    if not trusted or not enabled or not pin_type:
        return "BI"
    value = re.sub(r"[_-]+", " ", pin_type).strip().lower()
    if value in {"in", "input"}:
        return "IN"
    if value in {
        "out", "output", "open collector", "open emitter", "hiz", "tri state",
    }:
        return "OUT"
    return "BI"


def _inflate(box: dict, clearance: float) -> dict:
    return {
        "minX": box["minX"] - clearance,
        "maxX": box["maxX"] + clearance,
        "minY": box["minY"] - clearance,
        "maxY": box["maxY"] + clearance,
    }

def _intersects(left: dict, right: dict) -> bool:
    epsilon = 1e-6
    return not (
        left["maxX"] <= right["minX"] + epsilon or left["minX"] >= right["maxX"] - epsilon
        or left["maxY"] <= right["minY"] + epsilon or left["minY"] >= right["maxY"] - epsilon
    )


def _marker_box(net: str, point: dict, rotation: float, kind: str = "port", direction: str | None = None) -> dict:
    if kind == "flag":
        ground = net.upper() in {"GND", "AGND", "PGND"}
        extents = (
            {0: (-105, 105, -195, -95), 90: (95, 195, -105, 105), 180: (-105, 105, 95, 195), 270: (-195, -95, -105, 105)}
            if ground else
            {0: (-55, 55, 45, 105), 90: (-105, -45, -55, 55), 180: (-55, 55, -105, -45), 270: (45, 105, -55, 55)}
        )[int(rotation) % 360]
        return {"minX": point["x"] + extents[0], "maxX": point["x"] + extents[1], "minY": point["y"] + extents[2], "maxY": point["y"] + extents[3]}
    rotation = int(rotation) % 360
    if kind == "port" and direction == "IN":
        rotation = (rotation + 180) % 360
    if kind == "port":
        extents = {0: (95, 405, -55, 55), 90: (-55, 55, 95, 405), 180: (-405, -95, -55, 55), 270: (-55, 55, -405, -95)}[rotation]
        return {"minX": point["x"] + extents[0], "maxX": point["x"] + extents[1], "minY": point["y"] + extents[2], "maxY": point["y"] + extents[3]}
    width, height = 320, 120
    if rotation == 0:
        return {"minX": point["x"], "maxX": point["x"] + width,
                "minY": point["y"] - height / 2, "maxY": point["y"] + height / 2}
    if rotation == 180:
        return {"minX": point["x"] - width, "maxX": point["x"],
                "minY": point["y"] - height / 2, "maxY": point["y"] + height / 2}
    if rotation == 90:
        return {"minX": point["x"] - height / 2, "maxX": point["x"] + height / 2,
                "minY": point["y"], "maxY": point["y"] + width}
    return {"minX": point["x"] - height / 2, "maxX": point["x"] + height / 2,
            "minY": point["y"] - width, "maxY": point["y"]}


def _segment_hits_box(a: dict, b: dict, box: dict) -> bool:
    if a["x"] == b["x"]:
        low, high = sorted((a["y"], b["y"]))
        return box["minX"] < a["x"] < box["maxX"] and max(low, box["minY"]) < min(high, box["maxY"])
    if a["y"] == b["y"]:
        low, high = sorted((a["x"], b["x"]))
        return box["minY"] < a["y"] < box["maxY"] and max(low, box["minX"]) < min(high, box["maxX"])
    return True


def _segments_cross(a: dict, b: dict, c: dict, d: dict) -> bool:
    if a["x"] == b["x"] and c["x"] == d["x"]:
        return a["x"] == c["x"] and max(min(a["y"], b["y"]), min(c["y"], d["y"])) <= min(max(a["y"], b["y"]), max(c["y"], d["y"]))
    if a["y"] == b["y"] and c["y"] == d["y"]:
        return a["y"] == c["y"] and max(min(a["x"], b["x"]), min(c["x"], d["x"])) <= min(max(a["x"], b["x"]), max(c["x"], d["x"]))
    vertical_a = a["x"] == b["x"]
    v1, v2, h1, h2 = (a, b, c, d) if vertical_a else (c, d, a, b)
    return min(h1["x"], h2["x"]) <= v1["x"] <= max(h1["x"], h2["x"]) and min(v1["y"], v2["y"]) <= h1["y"] <= max(v1["y"], v2["y"])


def _compress_path(points: list[dict]) -> list[dict]:
    result = []
    for point in points:
        if len(result) >= 2:
            a, b = result[-2], result[-1]
            if (a["x"] == b["x"] == point["x"]) or (a["y"] == b["y"] == point["y"]):
                result[-1] = point
                continue
        result.append(point)
    return result


def _grid_route(start: dict, end: dict, components: list[dict], wires: list[dict], own: dict, grid: int = 50):
    """Bounded deterministic A* fallback for crowded marker lanes."""
    boxes = []
    own_items = tuple(own) if isinstance(own, (list, tuple)) else (own,)
    for item in components:
        if not item.get("bbox"):
            continue
        boxes.append(item["bbox"] if any(item is value for value in own_items) else _inflate(item["bbox"], 100))
    occupied = [(a, b) for wire in wires for a, b in zip(wire.get("points", []), wire.get("points", [])[1:])]
    xs = [start["x"], end["x"], *(value for box in boxes for value in (box["minX"], box["maxX"]))]
    ys = [start["y"], end["y"], *(value for box in boxes for value in (box["minY"], box["maxY"]))]
    bounds = (min(xs) - 600, max(xs) + 600, min(ys) - 600, max(ys) + 600)
    source, target = (start["x"], start["y"]), (end["x"], end["y"])

    def edge_clear(left, right):
        a, b = {"x": left[0], "y": left[1]}, {"x": right[0], "y": right[1]}
        if any(_segment_hits_box(a, b, box) for box in boxes):
            return False
        return not any(_segments_cross(a, b, c, d) for c, d in occupied)

    queue = [(abs(source[0] - target[0]) + abs(source[1] - target[1]), 0, source)]
    previous, cost = {}, {source: 0}
    while queue and len(cost) <= 50000:
        _, current_cost, current = heapq.heappop(queue)
        if current == target:
            path = [current]
            while current != source:
                current = previous[current]
                path.append(current)
            return _compress_path([{"x": x, "y": y} for x, y in reversed(path)])
        if current_cost != cost.get(current):
            continue
        neighbors = [
            (current[0] - grid, current[1]), (current[0] + grid, current[1]),
            (current[0], current[1] - grid), (current[0], current[1] + grid),
        ]
        neighbors.sort(key=lambda point: (abs(point[0] - target[0]) + abs(point[1] - target[1]), point))
        for neighbor in neighbors:
            if not (bounds[0] <= neighbor[0] <= bounds[1] and bounds[2] <= neighbor[1] <= bounds[3]):
                continue
            if not edge_clear(current, neighbor):
                continue
            pending = current_cost + grid
            if pending < cost.get(neighbor, float("inf")):
                cost[neighbor] = pending
                previous[neighbor] = current
                priority = pending + abs(neighbor[0] - target[0]) + abs(neighbor[1] - target[1])
                heapq.heappush(queue, (priority, pending, neighbor))
    return None


def _candidate_clear(box: dict, path: list[dict], component_boxes: list[dict], marker_boxes: list[dict], marker_component_boxes: list[dict] | None = None, wires: list[dict] | None = None) -> bool:
    return (
        not any(_intersects(box, other) for other in (marker_component_boxes or component_boxes) + marker_boxes)
        and not any(_segment_hits_box(a, b, other) for a, b in zip(path, path[1:]) for other in component_boxes)
        and not any(_segment_hits_box(a, b, box) for wire in wires or [] for a, b in zip(wire.get("points", []), wire.get("points", [])[1:]))
        and not any(_segments_cross(a, b, c, d) for a, b in zip(path, path[1:]) for wire in wires or [] for c, d in zip(wire.get("points", []), wire.get("points", [])[1:]))
    )


def _find_existing_wire(state: dict, net: str, start: dict, end: dict):
    wanted = {(start["x"], start["y"]), (end["x"], end["y"])}
    for wire in state.get("wires", []):
        points = wire.get("points") or []
        if wire.get("net") == net and len(points) >= 2 and {
            (points[0]["x"], points[0]["y"]), (points[-1]["x"], points[-1]["y"]),
        } == wanted:
            return points if (points[0]["x"], points[0]["y"]) == (start["x"], start["y"]) else list(reversed(points))
    return None


def _resolved_branch(net: str, index: int, anchor: str, start: dict, end: dict, path: list[dict], role: str) -> dict:
    return {
        "client_id": f"plan/{net}/{role}/{index}", "start": anchor, "end": end,
        "waypoints": path[1:-1], "role": role, "anchor": anchor if role == "stub" else None,
    }


def resolve_plan(plan: dict, state: dict) -> dict:
    """Resolve logical connection intents against exact live pin geometry."""
    if plan.get("format") != "schematic-plan/v0.2" or not plan.get("connection_intents"):
        return _error("PLAN_INVALID", "a schematic-plan/v0.2 with connection intents is required")
    pins = _pin_index(state)
    missing = sorted({ep["selector"] for row in plan["connection_intents"] for ep in row["endpoints"]} - pins.keys(), key=natural_key)
    if missing:
        return _error("PIN_NOT_FOUND", "live schematic is missing planned pins", selectors=missing)
    options = plan.get("options") or {}
    clearance = float(options.get("marker_clearance_mil", 100))
    lengths = [require_grid(value) for value in options.get("stub_lengths_mil", [200, 300, 400, 500, 600])]
    marker_boxes, wires, labels, ports, flags, fallbacks = [], [], [], [], [], []
    occupied = list(state.get("wires", []))
    resolved_count = marker_count = direct_count = 0

    def intent_order(item: dict):
        if item.get("strategy") == "direct":
            priority = 0
        elif item.get("strategy") == "flag":
            priority = 1 if item.get("kind") == "ground" else 2
        else:
            priority = 3
        return priority, natural_key(item["net"])

    for intent in sorted(plan["connection_intents"], key=intent_order):
        net, endpoints, strategy = intent["net"], intent["endpoints"], intent["strategy"]
        if strategy == "direct" and len(endpoints) == 2:
            first_component, first = pins[endpoints[0]["selector"]]
            second_component, second = pins[endpoints[1]["selector"]]
            start = {"x": first["x"], "y": first["y"]}
            end = {"x": second["x"], "y": second["y"]}
            distance = abs(start["x"] - end["x"]) + abs(start["y"] - end["y"])
            if distance >= options.get("cross_region_distance_mil", 2000):
                strategy = "port"
                fallbacks.append({
                    "net": net, "from": "direct", "to": "port",
                    "reason": "spatially_cross_region", "distance_mil": distance,
                })
            else:
                other_wires = [item for item in occupied if item.get("net") != net]
                path = _find_existing_wire(state, net, start, end) or route_orthogonal(
                    [start, end], state.get("components", []), other_wires
                )
                path = path or _grid_route(
                    start, end, state.get("components", []), other_wires,
                    (first_component, second_component),
                )
                if not path:
                    strategy = "port"
                    fallbacks.append({"net": net, "from": "direct", "to": "port", "reason": "route_blocked"})
                else:
                    wires.append({"net": net, "branches": [_resolved_branch(net, 0, endpoints[0]["selector"], start, end, path, "direct")]})
                    occupied.append({"net": net, "points": path})
                    resolved_count += 2
                    direct_count += 2
                    continue

        branches = []
        target_kind = "flag" if strategy == "flag" else "label" if strategy == "label" else "port"
        for index, endpoint in enumerate(endpoints):
            anchor = endpoint["selector"]
            component, pin = pins[anchor]
            side = _side(component, pin)
            vector = VECTORS[side]
            rotation = ROTATIONS[side]
            start = {"x": pin["x"], "y": pin["y"]}
            marker_direction = _direction(
                endpoint.get("pin_type"), endpoint.get("pin_type_trusted", False),
                options.get("use_trusted_pin_directions", True),
            ) if target_kind == "port" else None
            chosen = None
            obstacles = [
                _inflate(item["bbox"], clearance)
                for item in state.get("components", [])
                if item is not component and item.get("bbox")
            ]
            marker_obstacles = [
                _inflate(item["bbox"], clearance)
                for item in state.get("components", []) if item.get("bbox")
            ]
            unrelated_wires = [item for item in occupied if item.get("net") != net]
            for length in lengths:
                point = {"x": start["x"] + vector[0] * length, "y": start["y"] + vector[1] * length}
                path = [start, point]
                box = _marker_box(net, point, rotation, target_kind, marker_direction)
                if _candidate_clear(box, path, obstacles, marker_boxes, marker_obstacles, unrelated_wires):
                    chosen = point, path, box, side
                if chosen:
                    break
            if chosen is None:
                offsets = [value for step in range(1, 31) for value in (step * 200, -step * 200)]
                for length in reversed(lengths):
                    for offset in offsets:
                        point = {
                            "x": start["x"] + vector[0] * length + (offset if side in {"top", "bottom"} else 0),
                            "y": start["y"] + vector[1] * length + (offset if side in {"left", "right"} else 0),
                        }
                        other_wires = [item for item in occupied if item.get("net") != net]
                        path = route_orthogonal([start, point], state.get("components", []), other_wires)
                        path = path or _grid_route(start, point, state.get("components", []), other_wires, component)
                        if path:
                            box = _marker_box(net, point, rotation, target_kind, marker_direction)
                            if _candidate_clear(box, path, obstacles, marker_boxes, marker_obstacles, unrelated_wires):
                                chosen = point, path, box, side
                                fallbacks.append({"net": net, "anchor": anchor, "to": "local_lane", "side": side})
                        if chosen:
                            break
                    if chosen:
                        break
            if chosen is None:
                all_boxes = [item["bbox"] for item in state.get("components", []) if item.get("bbox")]
                bounds = {
                    "left": min(box["minX"] for box in all_boxes) - 300,
                    "right": max(box["maxX"] for box in all_boxes) + 300,
                    "top": min(box["minY"] for box in all_boxes) - 300,
                    "bottom": max(box["maxY"] for box in all_boxes) + 300,
                }
                offsets = [0] + [value for step in range(1, 31) for value in (step * 200, -step * 200)]
                for lane_side in (side, *(name for name in SIDES if name != side)):
                    for offset in offsets:
                        point = ({"x": bounds[lane_side], "y": start["y"] + offset}
                                 if lane_side in {"left", "right"}
                                 else {"x": start["x"] + offset, "y": bounds[lane_side]})
                        other_wires = [item for item in occupied if item.get("net") != net]
                        path = route_orthogonal([start, point], state.get("components", []), other_wires)
                        path = path or _grid_route(start, point, state.get("components", []), other_wires, component)
                        box = _marker_box(net, point, rotation, target_kind, marker_direction)
                        if path and _candidate_clear(box, path, obstacles, marker_boxes, marker_obstacles, unrelated_wires):
                            chosen = point, path, box, side
                            fallbacks.append({"net": net, "anchor": anchor, "to": "outer_lane", "side": side})
                            break
                    if chosen:
                        break
            if chosen is None:
                return _error("READABILITY_UNRESOLVED", f"no collision-free marker position for {anchor}", net=net, anchor=anchor)
            point, path, box, marker_side = chosen
            side = marker_side
            rotation = ROTATIONS[side]
            branches.append(_resolved_branch(net, index, anchor, start, point, path, "stub"))
            occupied.append({"net": net, "points": path})
            marker_boxes.append(box)
            marker = {
                "client_id": f"plan/{net}/{target_kind}/{index}", "net": net,
                "at": point, "rotation": rotation, "mirror": False,
                "anchor": anchor, "side": side,
            }
            if target_kind == "flag":
                marker["identification"] = "Ground" if intent.get("kind") == "ground" else "Power"
                flags.append(marker)
            elif target_kind == "label":
                labels.append(marker)
            else:
                marker["direction"] = marker_direction
                ports.append(marker)
            marker_count += 1
            resolved_count += 1
        wires.append({"net": net, "branches": branches})

    result = copy.deepcopy(plan)
    if options.get("preserve_existing_placements"):
        live = {item.get("designator"): item for item in state.get("components", [])}
        for placement in result.get("placements", []):
            found = live.get(placement.get("designator"))
            if found:
                placement.update({
                    key: found.get(key)
                    for key in ("x", "y", "rotation", "mirror")
                })
    result.update({
        "format": "schematic-plan/v0.2", "phase": "resolved", "wires": wires,
        "labels": labels, "ports": ports, "flags": flags,
        "visual": {
            "expected_endpoints": sum(len(item["endpoints"]) for item in plan["connection_intents"]),
            "resolved_endpoints": resolved_count, "marker_endpoints": marker_count,
            "direct_endpoints": direct_count, "fallbacks": fallbacks,
        },
    })
    result.pop("plan_hash", None)
    result["plan_hash"] = _hash(result)
    return {"ok": True, "plan": result}


def _issue(code: str, **details) -> dict:
    stable = {"code": code, **details}
    return {"id": _hash(stable), **stable}


def _marker_rows(state: dict):
    for kind, key in (("label", "labels"), ("port", "ports"), ("flag", "flags")):
        for item in state.get(key, []):
            yield kind, item


def verify_readability(plan: dict, state: dict) -> dict:
    if plan.get("format") != "schematic-plan/v0.2" or plan.get("phase") != "resolved":
        return _error("PLAN_NOT_RESOLVED", "readability verification requires a resolved v0.2 plan")
    pins = _pin_index(state)
    issues, covered, expected = [], 0, 0
    actual_markers = list(_marker_rows(state))

    for kind, key in (("label", "labels"), ("port", "ports"), ("flag", "flags")):
        for marker in plan.get(key, []):
            expected += 1
            point = marker["at"]
            matches = [item for actual_kind, item in actual_markers if actual_kind == kind and item.get("net") == marker["net"] and item.get("x") == point["x"] and item.get("y") == point["y"]]
            if not matches:
                issues.append(_issue("VISIBLE_MARKER_MISSING", kind=kind, net=marker["net"], anchor=marker.get("anchor")))
                continue
            actual = matches[0]
            if actual.get("rotation") != marker.get("rotation"):
                issues.append(_issue("MARKER_ROTATION_MISMATCH", kind=kind, net=marker["net"], anchor=marker.get("anchor")))
            if kind == "port" and actual.get("direction_status") == "readback" and actual.get("direction") != marker.get("direction"):
                issues.append(_issue("PORT_DIRECTION_MISMATCH", net=marker["net"], anchor=marker.get("anchor")))
            covered += 1

    actual_wires = state.get("wires", [])
    for wire in plan.get("wires", []):
        for branch in wire.get("branches", []):
            expected += 2 if branch.get("role") == "direct" else 1
            start_value, end_value = branch["start"], branch["end"]
            start = pins.get(start_value, ({}, start_value))[1] if isinstance(start_value, str) else start_value
            end = pins.get(end_value, ({}, end_value))[1] if isinstance(end_value, str) else end_value
            endpoints = {(start["x"], start["y"]), (end["x"], end["y"])}
            matches = [item for item in actual_wires if item.get("net") == wire["net"] and len(item.get("points") or []) >= 2 and {(item["points"][0]["x"], item["points"][0]["y"]), (item["points"][-1]["x"], item["points"][-1]["y"])} == endpoints]
            if not matches:
                issues.append(_issue("VISIBLE_WIRE_MISSING", net=wire["net"], anchor=branch.get("anchor"), role=branch.get("role")))
            else:
                actual_path = matches[0].get("points") or []
                endpoint_components = {
                    match.group(1)
                    for value in (branch.get("start"), branch.get("end"))
                    if isinstance(value, str) and (match := PIN_SELECTOR.fullmatch(value))
                }
                for component in state.get("components", []):
                    if component.get("designator") not in endpoint_components and component.get("bbox") and any(
                        _segment_hits_box(a, b, component["bbox"])
                        for a, b in zip(actual_path, actual_path[1:])
                    ):
                        issues.append(_issue(
                            "WIRE_COMPONENT_CROSSING", wire_id=matches[0].get("id"),
                            component=component.get("designator"), net=wire["net"],
                        ))
                covered += 2 if branch.get("role") == "direct" else 1

    components = [item for item in state.get("components", []) if item.get("bbox")]
    marker_boxes = []
    for kind, marker in actual_markers:
        box = marker.get("bbox") or _marker_box(
            marker.get("net") or "", marker, marker.get("rotation") or 0,
            kind, marker.get("direction"),
        )
        marker_boxes.append((kind, marker, box))
        for component in components:
            if _intersects(box, component["bbox"]):
                issues.append(_issue("MARKER_COMPONENT_OVERLAP", marker_id=marker.get("id"), component=component.get("designator")))
    for index, (kind, marker, box) in enumerate(marker_boxes):
        for other_kind, other, other_box in marker_boxes[index + 1:]:
            if _intersects(box, other_box):
                issues.append(_issue("MARKER_MARKER_OVERLAP", marker_id=marker.get("id"), other_id=other.get("id"), kinds=sorted((kind, other_kind))))

    unique = {item["id"]: item for item in issues}
    rows = sorted(unique.values(), key=lambda item: (item["code"], item["id"]))
    return {
        "ok": not rows, "passed": not rows, "expected_endpoint_evidence": expected,
        "covered_endpoint_evidence": covered,
        "visible_endpoint_coverage": 1.0 if not expected else covered / expected,
        "issues": rows,
    }
