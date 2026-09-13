"""Public behavior for compact PCB layout reads and direct EasyEDA writes."""

from __future__ import annotations

import re
from collections import Counter

from .bridge_client import BridgeClient
from .layout_bridge import (
    auto_layout_program,
    auto_routing_program,
    capture_layout,
    create_route_program,
    edit_routing_program,
    outline_program,
    placement_program,
    pour_program,
    region_program,
    run_strict_drc,
)
from .layout_codec import (
    base_response,
    bbox_union_area,
    bbox_intersects,
    columnar,
    component_overlaps,
    layer_dictionary,
    layout_revision,
    net_dictionary,
    paginate,
    primitive_in_region,
    route_lengths,
)
from .layout_drc import drc_delta, flatten_drc

PIN_SELECTOR = re.compile(r"^(.+)\.#([^#]+)$")


def _read_state(client: BridgeClient):
    response = capture_layout(client)
    if not response.get("ok"):
        return None, response
    return response["result"], None


def _error(code: str, message: str, **extra) -> dict:
    return {"ok": False, "code": code, "message": message, **extra}


def _board_bbox(state: dict) -> dict | None:
    points = []
    for key in ("lines", "arcs"):
        for item in state.get(key, []):
            if item.get("layer") == 11:
                points.extend(
                    ((item["start_x"], item["start_y"]), (item["end_x"], item["end_y"]))
                )
    for item in state.get("polylines", []):
        if item.get("layer") == 11 and item.get("bbox"):
            box = item["bbox"]
            points.extend(((box["minX"], box["minY"]), (box["maxX"], box["maxY"])))
    if not points:
        boxes = [
            item.get("bbox") for item in state.get("components", []) if item.get("bbox")
        ]
        for box in boxes:
            points.extend(((box["minX"], box["minY"]), (box["maxX"], box["maxY"])))
    if not points:
        return None
    xs, ys = zip(*points)
    return {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}


def _drc_rows(client: BridgeClient):
    response = run_strict_drc(client)
    if not response.get("ok"):
        return None, response
    return flatten_drc(response.get("result") or []), None


def get_layout_summary(
    client: BridgeClient, cursor: int | None = None, page_size: int = 100
) -> dict:
    state, error = _read_state(client)
    if error:
        return error
    violations, error = _drc_rows(client)
    if error:
        return error
    components = sorted(
        state.get("components", []), key=lambda row: row.get("designator") or ""
    )
    page, next_cursor = paginate(components, cursor, page_size)
    lengths = route_lengths(state)
    nets = []
    for item in sorted(state.get("nets", []), key=lambda row: row.get("net") or ""):
        route = lengths.get(item.get("net") or "", {})
        nets.append(
            {
                "net": item.get("net"),
                "eda_length": item.get("length"),
                "trace_length": route.get("total", 0),
                "vias": route.get("vias", 0),
            }
        )
    bbox = _board_bbox(state)
    outside = []
    if bbox:
        for component in components:
            item = component.get("bbox")
            if item and not (
                bbox["minX"] <= item["minX"] <= item["maxX"] <= bbox["maxX"]
                and bbox["minY"] <= item["minY"] <= item["maxY"] <= bbox["maxY"]
            ):
                outside.append(component.get("designator"))
    connection_types = ("connection", "unrouted", "unconnected", "未布线", "未连接")
    unrouted_by_net = Counter(
        row.get("net") or ""
        for row in violations
        if any(
            token in str(row.get("type") or "").lower() for token in connection_types
        )
    )
    board_area = (
        max(0, bbox["maxX"] - bbox["minX"]) * max(0, bbox["maxY"] - bbox["minY"])
        if bbox
        else 0
    )
    component_area = bbox_union_area(
        item.get("bbox") for item in components if item.get("bbox")
    )
    for item in nets:
        count = unrouted_by_net.get(item.get("net") or "", 0)
        item["unrouted_drc_count"] = count
        item["complete_by_strict_drc"] = count == 0
    response = base_response(
        state,
        {
            "kind": "board-summary",
            "cursor": max(0, int(cursor or 0)),
            "page_size": max(1, min(int(page_size), 500)),
        },
    )
    response.update(
        {
            "ok": True,
            "board_bbox": bbox,
            "counts": {
                "components": len(components),
                "nets": len(state.get("nets", [])),
                "lines": len(state.get("lines", [])),
                "arcs": len(state.get("arcs", [])),
                "vias": len(state.get("vias", [])),
                "pours": len(state.get("pours", [])),
                "poured": len(state.get("poured", [])),
                "regions": len(state.get("regions", [])),
                "violations": len(violations),
            },
            "components": columnar(
                page, ["designator", "x", "y", "rotation", "layer", "locked", "bbox"]
            ),
            "nets": columnar(
                nets,
                [
                    "net",
                    "eda_length",
                    "trace_length",
                    "vias",
                    "unrouted_drc_count",
                    "complete_by_strict_drc",
                ],
            ),
            "dicts": {"layers": layer_dictionary(state)},
            "facts": {
                "bbox_overlaps": component_overlaps(components),
                "bbox_outside_board": outside,
                "component_bbox_union_area": component_area,
                "board_bbox_area": board_area,
                "component_bbox_occupancy": component_area / board_area
                if board_area
                else None,
                "violations_by_type": dict(
                    sorted(Counter(row["type"] for row in violations).items())
                ),
            },
            "next_cursor": next_cursor,
        }
    )
    return response


def get_layout_components(
    client: BridgeClient,
    designators: list[str] | None = None,
    region: dict | None = None,
    include_pads: bool = False,
) -> dict:
    state, error = _read_state(client)
    if error:
        return error
    wanted = set(designators or [])
    rows = [
        item
        for item in state.get("components", [])
        if (not wanted or item.get("designator") in wanted)
        and bbox_intersects(item.get("bbox"), region)
    ]
    found = {item.get("designator") for item in rows}
    if wanted - found:
        return _error(
            "COMPONENT_NOT_FOUND",
            "components not found: " + ", ".join(sorted(wanted - found)),
        )
    fields = [
        "designator",
        "id",
        "name",
        "footprint",
        "x",
        "y",
        "rotation",
        "layer",
        "locked",
        "bbox",
    ]
    net_names, net_refs = net_dictionary(state)
    response = base_response(
        state,
        {
            "kind": "components",
            "designators": sorted(wanted),
            "region": region,
            "include_pads": include_pads,
        },
    )
    response.update(
        {
            "ok": True,
            "components": columnar(
                sorted(rows, key=lambda row: row.get("designator") or ""), fields
            ),
            "dicts": {"layers": layer_dictionary(state), "nets": net_names},
        }
    )
    if include_pads:
        pads = []
        for component in rows:
            for pad in component.get("pads", []):
                pads.append(
                    {
                        **pad,
                        "designator": component.get("designator"),
                        "net": net_refs.get(str(pad.get("net")))
                        if pad.get("net") is not None
                        else None,
                    }
                )
        response["pads"] = columnar(
            sorted(
                pads,
                key=lambda row: (
                    row.get("designator") or "",
                    str(row.get("number") or ""),
                ),
            ),
            [
                "designator",
                "id",
                "number",
                "net",
                "layer",
                "x",
                "y",
                "rotation",
                "bbox",
            ],
        )
    return response


def get_layout_routing(
    client: BridgeClient, nets: list[str] | None = None, region: dict | None = None
) -> dict:
    state, error = _read_state(client)
    if error:
        return error
    wanted = set(nets or [])
    copper_layers = {
        item.get("id")
        for item in state.get("layers", [])
        if item.get("type") in {"SIGNAL", "PLANE"}
    }
    response = base_response(
        state,
        {"kind": "routing", "nets": sorted(wanted), "region": region},
    )
    net_names, net_refs = net_dictionary(state)
    response["ok"] = True
    response["dicts"] = {"layers": layer_dictionary(state), "nets": net_names}
    specs = {
        "lines": [
            "id",
            "net",
            "layer",
            "start_x",
            "start_y",
            "end_x",
            "end_y",
            "width",
            "locked",
        ],
        "arcs": [
            "id",
            "net",
            "layer",
            "start_x",
            "start_y",
            "end_x",
            "end_y",
            "angle",
            "width",
            "locked",
        ],
        "vias": [
            "id",
            "net",
            "x",
            "y",
            "hole_diameter",
            "diameter",
            "via_type",
            "blind_via_rule",
            "locked",
        ],
        "polylines": ["id", "net", "layer", "polygon", "width", "locked"],
    }
    for key, fields in specs.items():
        rows = [
            item
            for item in state.get(key, [])
            if (key == "vias" or item.get("layer") in copper_layers)
            and (not wanted or item.get("net") in wanted)
            and primitive_in_region(item, region)
        ]
        response[key] = columnar(
            [
                {
                    **item,
                    "net": net_refs.get(str(item.get("net")))
                    if item.get("net") is not None
                    else None,
                }
                for item in rows
            ],
            fields,
        )
    selected = {
        key: [
            item
            for item in state.get(key, [])
            if (key == "vias" or item.get("layer") in copper_layers)
            and (not wanted or item.get("net") in wanted)
        ]
        for key in ("lines", "arcs", "vias")
    }
    response["facts"] = {"lengths": route_lengths(selected)}
    return response


def get_board_geometry(client: BridgeClient) -> dict:
    state, error = _read_state(client)
    if error:
        return error
    response = base_response(state, {"kind": "board-geometry"})
    response.update(
        {
            "ok": True,
            "board_bbox": _board_bbox(state),
            "layers": columnar(
                state.get("layers", []),
                ["id", "name", "type", "layerStatus", "locked"],
            ),
            "stacking": state.get("stacking"),
            "outline": {
                "lines": [
                    item for item in state.get("lines", []) if item.get("layer") == 11
                ],
                "arcs": [
                    item for item in state.get("arcs", []) if item.get("layer") == 11
                ],
                "polylines": [
                    item
                    for item in state.get("polylines", [])
                    if item.get("layer") == 11
                ],
            },
            "keepouts": state.get("regions", []),
            "pours": state.get("pours", []),
            "poured": state.get("poured", []),
            "obstacles": columnar(state.get("obstacles", []), ["id", "type", "bbox"]),
        }
    )
    return response


def get_layout_rules(client: BridgeClient) -> dict:
    state, error = _read_state(client)
    if error:
        return error
    response = base_response(state, {"kind": "layout-rules"})
    response.update(
        {
            "ok": True,
            "rules": state.get("rules"),
            "net_classes": state.get("net_classes", []),
            "differential_pairs": state.get("differential_pairs", []),
        }
    )
    return response


def get_layout_violations(
    client: BridgeClient,
    ids: list[str] | None = None,
    nets: list[str] | None = None,
    region: dict | None = None,
) -> dict:
    state, error = _read_state(client)
    if error:
        return error
    rows, error = _drc_rows(client)
    if error:
        return error
    wanted_ids, wanted_nets = set(ids or []), set(nets or [])
    filtered = []
    for row in rows:
        if wanted_ids and row["id"] not in wanted_ids:
            continue
        if wanted_nets and row.get("net") not in wanted_nets:
            continue
        pos = row.get("position") or {}
        x, y = pos.get("x"), pos.get("y")
        inside_region = (
            bool(
                x is not None
                and y is not None
                and min(region["left"], region["right"])
                <= x
                <= max(region["left"], region["right"])
                and min(region["bottom"], region["top"])
                <= y
                <= max(region["bottom"], region["top"])
            )
            if region
            else True
        )
        if not inside_region:
            continue
        filtered.append(row)
    response = base_response(
        state,
        {
            "kind": "violations",
            "ids": sorted(wanted_ids),
            "nets": sorted(wanted_nets),
            "region": region,
        },
    )
    response.update(
        {
            "ok": True,
            "passed": not rows,
            "total_count": len(rows),
            "matched_count": len(filtered),
            "violations": columnar(
                filtered,
                [
                    "id",
                    "type",
                    "object_type",
                    "rule",
                    "net",
                    "objects",
                    "position",
                    "message",
                    "source_id",
                ],
            ),
        }
    )
    return response


_READBACK_FIELDS = {
    "components": (
        "id",
        "designator",
        "x",
        "y",
        "rotation",
        "layer",
        "locked",
        "bbox",
        "pads",
    ),
    "lines": (
        "id",
        "net",
        "layer",
        "start_x",
        "start_y",
        "end_x",
        "end_y",
        "width",
        "locked",
    ),
    "arcs": (
        "id",
        "net",
        "layer",
        "start_x",
        "start_y",
        "end_x",
        "end_y",
        "angle",
        "width",
        "locked",
    ),
    "vias": (
        "id",
        "net",
        "x",
        "y",
        "hole_diameter",
        "diameter",
        "via_type",
        "blind_via_rule",
        "locked",
    ),
    "polylines": ("id", "net", "layer", "polygon", "width", "locked", "bbox"),
    "pours": (
        "id",
        "net",
        "layer",
        "polygon",
        "fill_method",
        "preserve_islands",
        "name",
        "priority",
        "width",
        "locked",
        "bbox",
    ),
    "poured": ("id", "pour_id", "fills", "bbox"),
    "regions": (
        "id",
        "layer",
        "polygon",
        "rule_types",
        "name",
        "width",
        "locked",
        "bbox",
    ),
}


def _write_readback(before: dict, after: dict) -> dict:
    changes = {}
    for kind, fields in _READBACK_FIELDS.items():
        before_by_id = {item.get("id"): item for item in before.get(kind, [])}
        after_by_id = {item.get("id"): item for item in after.get(kind, [])}
        created_ids = sorted(after_by_id.keys() - before_by_id)
        deleted_ids = sorted(before_by_id.keys() - after_by_id)
        modified_ids = sorted(
            key
            for key in before_by_id.keys() & after_by_id
            if before_by_id[key] != after_by_id[key]
        )
        if not created_ids and not deleted_ids and not modified_ids:
            continue

        def project(item):
            return {field: item.get(field) for field in fields}

        changes[kind] = {
            "created": [project(after_by_id[key]) for key in created_ids],
            "modified": [project(after_by_id[key]) for key in modified_ids],
            "deleted": deleted_ids,
        }
    return {
        "source": "easyeda-pro-live",
        "unit": "mil",
        "revision": layout_revision(after),
        "changes": changes,
    }


def _checked_write(client: BridgeClient, expected_revision: str, program: str) -> dict:
    before, error = _read_state(client)
    if error:
        return error
    revision_before = layout_revision(before)
    if expected_revision != revision_before:
        return _error(
            "STALE_LAYOUT",
            "layout changed since it was read; fetch a fresh snapshot before writing",
            expected_revision=expected_revision,
            current_revision=revision_before,
        )
    drc_before, error = _drc_rows(client)
    if error:
        return _error(
            "DRC_BASELINE_FAILED",
            "strict PCB DRC failed before the write; no change was applied",
            cause=error,
        )
    mutation = client.execute(program)
    if not mutation.get("ok"):
        return {
            **mutation,
            "applied": False,
            "partial": False,
            "revision_before": revision_before,
            "revision_after": revision_before,
            "results": [],
            "readback": {
                "source": "easyeda-pro-live",
                "unit": "mil",
                "revision": revision_before,
                "changes": {},
            },
            "drc": {
                "before_count": len(drc_before),
                "new": [],
                "resolved": [],
                "remaining_count": len(drc_before),
            },
        }
    result = mutation.get("result")
    if isinstance(result, list):
        failures = [item for item in result if not item.get("ok")]
        successes = [item for item in result if item.get("ok")]
        applied = bool(successes)
        partial = bool(successes and failures)
    else:
        failures = []
        applied = not (
            result is False
            or result is None
            or (isinstance(result, dict) and result.get("success") is False)
        )
        partial = bool(
            applied
            and isinstance(result, dict)
            and (result.get("failedComponents") or result.get("failedNets"))
        )
    after, read_error = _read_state(client)
    drc_after, drc_error = _drc_rows(client)
    if read_error or drc_error:
        return _error(
            "WRITE_VERIFICATION_FAILED",
            "EDA write returned, but layout readback or strict DRC failed",
            applied=applied,
            partial=True,
            revision_before=revision_before,
            revision_after=layout_revision(after) if after else None,
            results=result,
            readback_error=read_error,
            drc_error=drc_error,
        )
    response = {
        "ok": applied and not failures and not partial,
        "applied": applied,
        "partial": partial,
        "revision_before": revision_before,
        "revision_after": layout_revision(after),
        "results": result if isinstance(result, list) else [result],
        "readback": _write_readback(before, after),
        "drc": drc_delta(drc_before, drc_after),
    }
    if partial:
        response.update(
            {
                "code": "PARTIAL_APPLY",
                "message": "some requested operations failed after other changes applied",
            }
        )
    elif failures or not applied:
        response.update(
            {"code": "EDA_WRITE_REJECTED", "message": "EasyEDA rejected the write"}
        )
    return response


def _component_maps(state: dict):
    by_ref = {}
    pins = {}
    for component in state.get("components", []):
        ref = component.get("designator")
        if ref in by_ref:
            return (
                None,
                None,
                _error("AMBIGUOUS_COMPONENT", f"duplicate designator '{ref}'"),
            )
        by_ref[ref] = component
        for pin in component.get("pads", []):
            pins[f"{ref}.#{pin.get('number')}"] = pin
    return by_ref, pins, None


def _layer_ids(state: dict, *, copper_only: bool = False) -> set[int]:
    return {
        item.get("id")
        for item in state.get("layers", [])
        if not copper_only or item.get("type") in {"SIGNAL", "PLANE"}
    }


def _validate_layer(layer, known_layers: set[int], context: str) -> dict | None:
    if layer is not None and layer not in known_layers:
        return _error("INVALID_LAYER", f"{context} layer '{layer}' is unavailable")
    return None


def _resolve_anchor(
    anchor: str, by_ref: dict, pins: dict
) -> tuple[float, float] | None:
    if anchor in by_ref:
        return by_ref[anchor]["x"], by_ref[anchor]["y"]
    if PIN_SELECTOR.fullmatch(anchor) and anchor in pins:
        return pins[anchor]["x"], pins[anchor]["y"]
    return None


def set_component_placement(
    client: BridgeClient, expected_revision: str, edits: list[dict]
) -> dict:
    if not edits:
        return _error(
            "INVALID_EDIT", "edits must contain at least one component change"
        )
    state, error = _read_state(client)
    if error:
        return error
    current_revision = layout_revision(state)
    if current_revision != expected_revision:
        return _error(
            "STALE_LAYOUT",
            "layout changed since it was read; fetch a fresh snapshot before writing",
            expected_revision=expected_revision,
            current_revision=current_revision,
        )
    by_ref, pins, error = _component_maps(state)
    if error:
        return error
    prepared = []
    seen = set()
    for edit in edits:
        designator = edit.get("designator")
        if designator not in by_ref:
            return _error(
                "COMPONENT_NOT_FOUND", f"component '{designator}' was not found"
            )
        if designator in seen:
            return _error(
                "DUPLICATE_EDIT", f"component '{designator}' appears more than once"
            )
        seen.add(designator)
        properties = {}
        at = edit.get("at") or {}
        if "relative_to" in edit:
            if "x" in edit or "y" in edit or at:
                return _error(
                    "INVALID_EDIT",
                    f"component '{designator}' mixes relative and absolute positioning",
                )
            anchor = _resolve_anchor(str(edit["relative_to"]), by_ref, pins)
            if anchor is None:
                return _error(
                    "ANCHOR_NOT_FOUND", f"anchor '{edit['relative_to']}' was not found"
                )
            properties["x"] = anchor[0] + float(edit.get("dx", 0))
            properties["y"] = anchor[1] + float(edit.get("dy", 0))
        else:
            if at and ("x" in edit or "y" in edit):
                return _error(
                    "INVALID_EDIT",
                    f"component '{designator}' mixes at with top-level coordinates",
                )
            if "x" in edit or "x" in at:
                properties["x"] = float(edit.get("x", at.get("x")))
            if "y" in edit or "y" in at:
                properties["y"] = float(edit.get("y", at.get("y")))
        for source, target in (
            ("layer", "layer"),
            ("rotation", "rotation"),
            ("locked", "primitiveLock"),
        ):
            if source in edit:
                properties[target] = edit[source]
        if "layer" in properties and properties["layer"] not in {1, 2}:
            return _error(
                "INVALID_LAYER", "PCB components can only be placed on layer 1 or 2"
            )
        if not properties:
            return _error(
                "INVALID_EDIT", f"component '{designator}' has no changed property"
            )
        prepared.append({"id": by_ref[designator]["id"], "properties": properties})
    return _checked_write(client, expected_revision, placement_program(prepared))


def run_auto_layout(client: BridgeClient, expected_revision: str) -> dict:
    return _checked_write(client, expected_revision, auto_layout_program())


def run_auto_routing(
    client: BridgeClient,
    expected_revision: str,
    nets: list[str] | None = None,
    layers: list[int] | None = None,
    corner_style: str = "45",
    existing_mode: str = "keep",
    ignore_nets: list[str] | None = None,
) -> dict:
    if corner_style not in {"45", "90"}:
        return _error("INVALID_CORNER_STYLE", "corner_style must be '45' or '90'")
    if existing_mode not in {"keep", "remove"}:
        return _error(
            "INVALID_EXISTING_MODE", "existing_mode must be 'keep' or 'remove'"
        )
    state, error = _read_state(client)
    if error:
        return error
    current_revision = layout_revision(state)
    if current_revision != expected_revision:
        return _error(
            "STALE_LAYOUT",
            "layout changed since it was read; fetch a fresh snapshot before writing",
            expected_revision=expected_revision,
            current_revision=current_revision,
        )
    known_nets = {item.get("net") for item in state.get("nets", [])}
    unknown_nets = (set(nets or []) | set(ignore_nets or [])) - known_nets
    if unknown_nets:
        return _error(
            "NET_NOT_FOUND", "networks not found: " + ", ".join(sorted(unknown_nets))
        )
    copper_layers = _layer_ids(state, copper_only=True)
    unknown_layers = set(layers or []) - copper_layers
    if unknown_layers:
        return _error(
            "INVALID_LAYER",
            "non-copper or unavailable layers: "
            + ", ".join(map(str, sorted(unknown_layers))),
        )
    props = {
        "cornerStyle": 0 if corner_style == "45" else 1,
        "existingPrimitiveMode": existing_mode,
    }
    if nets:
        props["RoutingNets"] = nets
    if layers:
        props["layers"] = layers
    if ignore_nets:
        props["ignoreNets"] = ignore_nets
    return _checked_write(client, expected_revision, auto_routing_program(props))


def _route_point(value, pins: dict, default_layer: int):
    if isinstance(value, str):
        pin = pins.get(value)
        if pin is None:
            return None, f"pad selector '{value}' was not found"
        layer = pin.get("layer")
        if layer == 12 or layer is None:
            layer = default_layer
        return {"x": pin["x"], "y": pin["y"], "layer": layer, "selector": value}, None
    if not isinstance(value, dict) or "x" not in value or "y" not in value:
        return None, "route points must be pad selectors or {x, y, layer?} objects"
    return {
        "x": float(value["x"]),
        "y": float(value["y"]),
        "layer": int(value.get("layer", default_layer)),
    }, None


def create_route(
    client: BridgeClient,
    expected_revision: str,
    net: str,
    branches: list[dict],
    rule_overrides: dict | None = None,
) -> dict:
    if not branches:
        return _error("INVALID_ROUTE", "branches must contain at least one route")
    state, error = _read_state(client)
    if error:
        return error
    current_revision = layout_revision(state)
    if current_revision != expected_revision:
        return _error(
            "STALE_LAYOUT",
            "layout changed since it was read; fetch a fresh snapshot before writing",
            expected_revision=expected_revision,
            current_revision=current_revision,
        )
    known_nets = {item.get("net") for item in state.get("nets", [])}
    if net not in known_nets:
        return _error("NET_NOT_FOUND", f"network '{net}' was not found")
    _, pins, map_error = _component_maps(state)
    if map_error:
        return map_error
    overrides = rule_overrides or {}
    default_layer = int(overrides.get("layer", 1))
    copper_layers = _layer_ids(state, copper_only=True)
    if default_layer not in copper_layers:
        return _error(
            "INVALID_LAYER", f"layer '{default_layer}' is not an active copper layer"
        )
    operations = []
    for branch_index, branch in enumerate(branches):
        values = [
            branch.get("start"),
            *(branch.get("waypoints") or []),
            branch.get("end"),
        ]
        if values[0] is None or values[-1] is None:
            return _error("INVALID_ROUTE", f"branch {branch_index} needs start and end")
        points = []
        for value in values:
            point, point_error = _route_point(value, pins, default_layer)
            if point_error:
                return _error("INVALID_ROUTE_POINT", point_error, branch=branch_index)
            selector = point.get("selector")
            if selector and pins[selector].get("net") != net:
                return _error(
                    "PAD_NET_MISMATCH",
                    f"pad '{selector}' belongs to '{pins[selector].get('net')}', not '{net}'",
                )
            if point["layer"] not in copper_layers:
                return _error(
                    "INVALID_LAYER",
                    f"layer '{point['layer']}' is not an active copper layer",
                    branch=branch_index,
                )
            points.append(point)
        for start, end in zip(points, points[1:]):
            if start["x"] != end["x"] or start["y"] != end["y"]:
                operations.append(
                    {
                        "type": "line",
                        "layer": start["layer"],
                        "start_x": start["x"],
                        "start_y": start["y"],
                        "end_x": end["x"],
                        "end_y": end["y"],
                        "width": overrides.get("width"),
                    }
                )
            if start["layer"] != end["layer"]:
                if "hole_diameter" not in overrides or "diameter" not in overrides:
                    return _error(
                        "MISSING_VIA_DIMENSIONS",
                        "layer changes require hole_diameter and diameter in rule_overrides",
                    )
                operations.append(
                    {
                        "type": "via",
                        "x": end["x"],
                        "y": end["y"],
                        "hole_diameter": overrides["hole_diameter"],
                        "diameter": overrides["diameter"],
                        "via_type": overrides.get("via_type", 0),
                        "blind_via_rule": overrides.get("blind_via_rule"),
                    }
                )
    if not operations:
        return _error("INVALID_ROUTE", "route contains no segment or layer transition")
    return _checked_write(
        client, expected_revision, create_route_program(net, operations)
    )


def edit_routing(
    client: BridgeClient, expected_revision: str, actions: list[dict]
) -> dict:
    if not actions:
        return _error("INVALID_EDIT", "actions must not be empty")
    state, error = _read_state(client)
    if error:
        return error
    if layout_revision(state) != expected_revision:
        return _error(
            "STALE_LAYOUT",
            "layout changed since it was read; fetch a fresh snapshot before writing",
            expected_revision=expected_revision,
            current_revision=layout_revision(state),
        )
    indexes = {
        "line": {
            item["id"]: item
            for item in state.get("lines", [])
            if item.get("layer") != 11
        },
        "arc": {
            item["id"]: item
            for item in state.get("arcs", [])
            if item.get("layer") != 11
        },
        "via": {item["id"]: item for item in state.get("vias", [])},
    }
    known_nets = {item.get("net") for item in state.get("nets", [])}
    copper_layers = _layer_ids(state, copper_only=True)
    property_names = {
        "start_x": "startX",
        "start_y": "startY",
        "end_x": "endX",
        "end_y": "endY",
        "width": "lineWidth",
        "locked": "primitiveLock",
        "hole_diameter": "holeDiameter",
        "diameter": "diameter",
        "via_type": "viaType",
        "blind_via_rule": "designRuleBlindViaName",
        "x": "x",
        "y": "y",
        "net": "net",
        "layer": "layer",
        "angle": "arcAngle",
    }
    allowed_properties = {
        "line": {
            "net",
            "layer",
            "start_x",
            "start_y",
            "end_x",
            "end_y",
            "width",
            "locked",
        },
        "arc": {
            "net",
            "layer",
            "start_x",
            "start_y",
            "end_x",
            "end_y",
            "angle",
            "width",
            "locked",
        },
        "via": {
            "net",
            "x",
            "y",
            "hole_diameter",
            "diameter",
            "via_type",
            "blind_via_rule",
            "locked",
        },
    }
    prepared = []
    for action in actions:
        kind, operation, primitive_id = (
            action.get("type"),
            action.get("op"),
            action.get("id"),
        )
        if kind not in indexes or operation not in {"modify", "delete"}:
            return _error(
                "INVALID_EDIT",
                "routing action requires type line|arc|via and op modify|delete",
            )
        if primitive_id not in indexes[kind]:
            return _error(
                "PRIMITIVE_NOT_FOUND",
                f"{kind} '{primitive_id}' was not found or is not editable",
            )
        requested = action.get("properties") or {}
        unsupported = set(requested) - allowed_properties[kind]
        if unsupported:
            return _error(
                "INVALID_EDIT",
                f"{kind} '{primitive_id}' has unsupported properties: "
                + ", ".join(sorted(unsupported)),
            )
        properties = {
            property_names[key]: value
            for key, value in requested.items()
            if key in property_names
        }
        if requested.get("net") is not None and requested["net"] not in known_nets:
            return _error(
                "NET_NOT_FOUND", f"network '{requested['net']}' was not found"
            )
        layer_error = _validate_layer(
            requested.get("layer"), copper_layers, f"routing primitive '{primitive_id}'"
        )
        if layer_error:
            return layer_error
        if operation == "modify" and not properties:
            return _error(
                "INVALID_EDIT",
                f"modify action for '{primitive_id}' has no supported property",
            )
        prepared.append(
            {
                "type": kind,
                "op": operation,
                "id": primitive_id,
                "properties": properties,
            }
        )
    return _checked_write(client, expected_revision, edit_routing_program(prepared))


def set_board_outline(
    client: BridgeClient,
    expected_revision: str,
    contours: list[list[dict]],
    replace: bool = False,
) -> dict:
    if not contours or any(len(contour) < 3 for contour in contours):
        return _error(
            "INVALID_OUTLINE", "each outline contour needs at least three points"
        )
    for contour in contours:
        if any("x" not in point or "y" not in point for point in contour):
            return _error("INVALID_OUTLINE", "outline points require x and y")
    state, error = _read_state(client)
    if error:
        return error
    current_revision = layout_revision(state)
    if current_revision != expected_revision:
        return _error(
            "STALE_LAYOUT",
            "layout changed since it was read; fetch a fresh snapshot before writing",
            expected_revision=expected_revision,
            current_revision=current_revision,
        )
    if 11 not in _layer_ids(state):
        return _error("INVALID_LAYER", "BoardOutline layer 11 is unavailable")
    existing = {
        "line": [
            item["id"] for item in state.get("lines", []) if item.get("layer") == 11
        ],
        "arc": [
            item["id"] for item in state.get("arcs", []) if item.get("layer") == 11
        ],
        "polyline": [
            item["id"] for item in state.get("polylines", []) if item.get("layer") == 11
        ],
    }
    if any(existing.values()) and not replace:
        return _error(
            "OUTLINE_EXISTS",
            "the PCB already has an outline; pass replace=true to replace it explicitly",
        )
    normalized = [
        [
            {
                "x": float(point["x"]),
                "y": float(point["y"]),
                **({"width": float(point["width"])} if "width" in point else {}),
            }
            for point in contour
        ]
        for contour in contours
    ]
    return _checked_write(
        client, expected_revision, outline_program(normalized, replace, existing)
    )


def _validate_polygon_actions(actions: list[dict], valid_ops: set[str]) -> dict | None:
    if not actions:
        return _error("INVALID_EDIT", "actions must not be empty")
    for index, action in enumerate(actions):
        operation = action.get("op")
        if operation not in valid_ops:
            return _error(
                "INVALID_EDIT", f"action {index} has unsupported op '{operation}'"
            )
        if operation == "create" and not isinstance(action.get("polygon"), list):
            return _error(
                "INVALID_POLYGON",
                f"action {index} requires an EasyEDA polygon source array",
            )
        if action.get("polygon") is not None and not isinstance(
            action["polygon"], list
        ):
            return _error(
                "INVALID_POLYGON",
                f"action {index} polygon must be an EasyEDA polygon source array",
            )
        if operation != "create" and not action.get("id"):
            return _error("INVALID_EDIT", f"action {index} requires an id")
    return None


def edit_keepouts(
    client: BridgeClient, expected_revision: str, actions: list[dict]
) -> dict:
    error = _validate_polygon_actions(actions, {"create", "modify", "delete"})
    if error:
        return error
    state, read_error = _read_state(client)
    if read_error:
        return read_error
    current_revision = layout_revision(state)
    if current_revision != expected_revision:
        return _error(
            "STALE_LAYOUT",
            "layout changed since it was read; fetch a fresh snapshot before writing",
            expected_revision=expected_revision,
            current_revision=current_revision,
        )
    known = {item["id"] for item in state.get("regions", [])}
    known_layers = _layer_ids(state, copper_only=True)
    if 12 in _layer_ids(state):
        known_layers.add(12)
    prepared = []
    for action in actions:
        if action.get("op") != "create" and action.get("id") not in known:
            return _error(
                "PRIMITIVE_NOT_FOUND", f"region '{action.get('id')}' was not found"
            )
        if action.get("op") == "create" and not action.get("rule_types"):
            return _error("INVALID_EDIT", "new keepouts require at least one rule_type")
        invalid_rules = set(action.get("rule_types") or []) - {2, 5, 6, 7, 8, 9}
        if invalid_rules:
            return _error(
                "INVALID_RULE_TYPE",
                "unsupported keepout rule types: "
                + ", ".join(map(str, sorted(invalid_rules))),
            )
        if action.get("op") == "create" and action.get("layer") is None:
            return _error("INVALID_EDIT", "new keepouts require a layer")
        layer_error = _validate_layer(
            action.get("layer"),
            known_layers,
            f"keepout action for '{action.get('id') or 'new'}'",
        )
        if layer_error:
            return layer_error
        item = dict(action)
        if item.get("op") == "modify":
            item["properties"] = {
                key: value
                for key, value in {
                    "layer": item.get("layer"),
                    "ruleType": item.get("rule_types"),
                    "regionName": item.get("name"),
                    "lineWidth": item.get("width"),
                    "primitiveLock": item.get("locked"),
                }.items()
                if value is not None
            }
            if not item["properties"] and item.get("polygon") is None:
                return _error(
                    "INVALID_EDIT",
                    f"keepout '{item.get('id')}' has no changed property",
                )
        prepared.append(item)
    return _checked_write(client, expected_revision, region_program(prepared))


def edit_copper_pours(
    client: BridgeClient,
    expected_revision: str,
    actions: list[dict],
    rebuild: bool = True,
) -> dict:
    error = _validate_polygon_actions(actions, {"create", "modify", "delete"})
    if error:
        return error
    state, read_error = _read_state(client)
    if read_error:
        return read_error
    current_revision = layout_revision(state)
    if current_revision != expected_revision:
        return _error(
            "STALE_LAYOUT",
            "layout changed since it was read; fetch a fresh snapshot before writing",
            expected_revision=expected_revision,
            current_revision=current_revision,
        )
    known = {item["id"] for item in state.get("pours", [])}
    nets = {item.get("net") for item in state.get("nets", [])}
    copper_layers = _layer_ids(state, copper_only=True)
    prepared = []
    for action in actions:
        if action.get("op") != "create" and action.get("id") not in known:
            return _error(
                "PRIMITIVE_NOT_FOUND", f"pour '{action.get('id')}' was not found"
            )
        if action.get("op") == "create":
            if action.get("net") not in nets:
                return _error(
                    "NET_NOT_FOUND", f"network '{action.get('net')}' was not found"
                )
            if "layer" not in action:
                return _error("INVALID_EDIT", "new copper pours require a layer")
        if action.get("net") is not None and action.get("net") not in nets:
            return _error(
                "NET_NOT_FOUND", f"network '{action.get('net')}' was not found"
            )
        layer_error = _validate_layer(
            action.get("layer"),
            copper_layers,
            f"copper pour '{action.get('id') or 'new'}'",
        )
        if layer_error:
            return layer_error
        item = dict(action)
        if item.get("op") == "modify":
            item["properties"] = {
                key: value
                for key, value in {
                    "net": item.get("net"),
                    "layer": item.get("layer"),
                    "pourFillMethod": item.get("fill_method"),
                    "preserveSilos": item.get("preserve_islands"),
                    "pourName": item.get("name"),
                    "pourPriority": item.get("priority"),
                    "lineWidth": item.get("width"),
                    "primitiveLock": item.get("locked"),
                }.items()
                if value is not None
            }
            if not item["properties"] and item.get("polygon") is None:
                return _error(
                    "INVALID_EDIT",
                    f"copper pour '{item.get('id')}' has no changed property",
                )
        prepared.append(item)
    return _checked_write(client, expected_revision, pour_program(prepared, rebuild))
