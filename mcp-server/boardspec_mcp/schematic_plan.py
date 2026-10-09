"""Pure deterministic planning, diffing and topology comparison."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date

import boardspec
from boardspec.exporters import parse_protel2_netlist, render_protel2_netlist

from .core_tools import _load_spec
from .schematic_codec import natural_key, require_grid


SHEET_SIZES_MIL = {
    # EasyEDA's native landscape drawing sheets use rounded 10 mil units.
    # These conservative planning dimensions are confirmed again from the
    # live titleBlockData Width/Height fields after every native write.
    "A4": (11700.0, 8250.0),
    "A3": (16500.0, 11700.0),
}
SHEET_BORDER_MARGIN_MIL = 500.0
TITLE_BLOCK_WIDTH_MIL = 3600.0
TITLE_BLOCK_HEIGHT_MIL = 1200.0


def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _error(code: str, message: str, **extra):
    return {"ok": False, "code": code, "message": message, **extra}


def _geometry(options: dict, designator: str) -> dict[str, float]:
    value = options["measured_geometry"].get(designator, {})
    width, height = float(value.get("width", 400)), float(value.get("height", 400))
    return {
        "min_dx": float(value.get("min_dx", -width / 2)),
        "max_dx": float(value.get("max_dx", width / 2)),
        "min_dy": float(value.get("min_dy", -height / 2)),
        "max_dy": float(value.get("max_dy", height / 2)),
    }


def _layout_origins(ordered: list[dict], columns: int, options: dict) -> tuple[list[float], list[float]]:
    clearance = 400.0
    geometries = [_geometry(options, item["ref"]) for item in ordered]
    column_bounds, row_bounds = [], []
    for column in range(columns):
        values = geometries[column::columns]
        column_bounds.append((min(value["min_dx"] for value in values), max(value["max_dx"] for value in values)))
    rows = (len(ordered) + columns - 1) // columns
    for row in range(rows):
        values = geometries[row * columns : (row + 1) * columns]
        row_bounds.append((min(value["min_dy"] for value in values), max(value["max_dy"] for value in values)))

    x_origins, y_origins = [1000.0], [1000.0]
    for previous, current in zip(column_bounds, column_bounds[1:]):
        required = previous[1] - current[0] + clearance
        x_origins.append(x_origins[-1] + max(float(options["column_gap_mil"]), required))
    for previous, current in zip(row_bounds, row_bounds[1:]):
        required = previous[1] - current[0] + clearance
        y_origins.append(y_origins[-1] + max(float(options["row_gap_mil"]), required))
    grid = options["grid_mil"]
    return ([require_grid(math.ceil(value / grid) * grid, grid) for value in x_origins],
            [require_grid(math.ceil(value / grid) * grid, grid) for value in y_origins])


def _drawing_metadata(spec: dict, options: dict) -> tuple[dict | None, dict | None]:
    if options["drawing_profile"] == "legacy":
        return None, None
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    drawing = project.get("drawing") if isinstance(project.get("drawing"), dict) else {}
    required = {
        "/project/name": project.get("name"),
        "/project/version": project.get("version"),
        "/project/drawing/title": drawing.get("title"),
        "/project/drawing/number": drawing.get("number"),
    }
    missing = [
        {
            "code": "DRAWING_METADATA_REQUIRED",
            "path": path,
            "message": f"engineering_basic schematic planning requires {path}",
            "hint": "Add the field to BoardSpec project metadata or explicitly use drawing_profile=legacy.",
        }
        for path, value in required.items()
        if not str(value or "").strip()
    ]
    if missing:
        return None, _error(
            "DRAWING_METADATA_REQUIRED",
            "engineering drawing metadata is incomplete",
            errors=missing,
        )
    return {
        "project_name": str(project["name"]),
        "title": str(drawing["title"]),
        "number": str(drawing["number"]),
        "version": str(project["version"]),
        "date": str(drawing.get("date") or date.today().isoformat()),
        "page_number": 1,
        "page_count": 1,
        **{
            key: str(drawing[key])
            for key in ("company", "designer", "reviewer", "description")
            if drawing.get(key) not in (None, "")
        },
    }, None


def _content_bbox(placements: list[dict], options: dict) -> dict[str, float]:
    if not placements:
        return {"left": 1000.0, "top": 1000.0, "right": 1000.0, "bottom": 1000.0}
    boxes = []
    for item in placements:
        geometry = _geometry(options, item["designator"])
        boxes.append({
            "left": item["x"] + geometry["min_dx"],
            "right": item["x"] + geometry["max_dx"],
            "top": item["y"] + geometry["min_dy"],
            "bottom": item["y"] + geometry["max_dy"],
        })
    return {
        "left": min(item["left"] for item in boxes),
        "top": min(item["top"] for item in boxes),
        "right": max(item["right"] for item in boxes),
        "bottom": max(item["bottom"] for item in boxes),
    }


def _sheet(spec: dict, placements: list[dict], options: dict) -> tuple[dict | None, dict | None]:
    fields, error = _drawing_metadata(spec, options)
    if error or fields is None:
        return None, error
    content = _content_bbox(placements, options)
    requested = options["sheet_size"]
    candidates = ("A4", "A3") if requested == "auto" else (requested,)
    for size in candidates:
        width, height = SHEET_SIZES_MIL[size]
        usable = {
            "left": SHEET_BORDER_MARGIN_MIL,
            "top": SHEET_BORDER_MARGIN_MIL,
            "right": width - SHEET_BORDER_MARGIN_MIL,
            "bottom": height - SHEET_BORDER_MARGIN_MIL - TITLE_BLOCK_HEIGHT_MIL,
        }
        if (
            content["left"] >= usable["left"]
            and content["top"] >= usable["top"]
            and content["right"] <= usable["right"]
            and content["bottom"] <= usable["bottom"]
        ):
            return {
                "size": size,
                "orientation": "landscape",
                "width_mil": width,
                "height_mil": height,
                "border_margin_mil": SHEET_BORDER_MARGIN_MIL,
                "usable_rect": usable,
                "title_block_rect": {
                    "left": width - SHEET_BORDER_MARGIN_MIL - TITLE_BLOCK_WIDTH_MIL,
                    "top": height - SHEET_BORDER_MARGIN_MIL - TITLE_BLOCK_HEIGHT_MIL,
                    "right": width - SHEET_BORDER_MARGIN_MIL,
                    "bottom": height - SHEET_BORDER_MARGIN_MIL,
                },
                "content_bbox": content,
                "title_block": {
                    "visible": True,
                    "position": "bottom_right",
                    "fields": fields,
                    "editable_fields": [
                        "title",
                        "number",
                        "version",
                        "page_size",
                        *[
                            key
                            for key in (
                                "company",
                                "designer",
                                "reviewer",
                                "description",
                            )
                            if key in fields
                        ],
                    ],
                    "system_managed_fields": [
                        "project_name",
                        "date",
                        "page_number",
                        "page_count",
                    ],
                },
            }, None
    return None, _error(
        "SHEET_CAPACITY_EXCEEDED",
        f"planned content does not fit the requested {requested} landscape sheet policy",
        content_bbox=content,
        attempted=list(candidates),
        hint="Use A3, split the schematic into pages, or provide measured geometry and larger spacing deliberately.",
    )


def _resolver(yaml_text: str, base_dir: str | None = None):
    spec = _load_spec(yaml_text)
    if not spec:
        return None, [{"code": "SCHEMA_INVALID", "path": "/", "message": "specification is not a mapping"}]
    resolver, errors = boardspec.build_resolver(spec, base_dir or os.getcwd(), [])
    return resolver, errors


def build_plan(spec_yaml: str, options: dict | None = None) -> dict:
    options = {
        "page_policy": "single_page",
        "wiring_policy": "hybrid",
        "drawing_profile": "engineering_basic",
        "sheet_size": "auto",
        "net_annotation_policy": "every_endpoint",
        "grid_mil": 100,
        "column_gap_mil": 1000,
        "row_gap_mil": 600,
        "group_by_module": True,
        "high_fanout_primitive": "auto",
        "readability_policy": "engineering_basic",
        "stub_lengths_mil": [200, 300, 400, 500, 600],
        "marker_clearance_mil": 100,
        "cross_region_distance_mil": 2000,
        "use_trusted_pin_directions": True,
        "preserve_existing_placements": False,
        "measured_geometry": {},
        "base_dir": None,
        **(options or {}),
    }
    if options["net_annotation_policy"] == "sparse_named":
        options["wiring_policy"] = "continuous"
    spec = _load_spec(spec_yaml)
    if not spec:
        return _error("PLAN_INVALID", "BoardSpec is not a mapping")
    _, drawing_error = _drawing_metadata(spec, options)
    if drawing_error:
        return drawing_error
    warnings = []
    resolver, resolver_errors = _resolver(spec_yaml, options.get("base_dir"))
    if resolver_errors:
        return _error("PLAN_INVALID", "part library resolution failed", errors=resolver_errors, warnings=warnings)
    expanded, errors, warnings = boardspec.analyze(spec, resolver)
    if errors:
        return _error("PLAN_INVALID", "BoardSpec validation failed", errors=errors, warnings=warnings)
    components, nets = boardspec.build_flat(expanded, resolver)
    degree = {item["ref"]: 0 for item in components}
    for net in nets:
        for ref, _ in net["nodes"]:
            degree[ref] = degree.get(ref, 0) + 1
    ordered = sorted(
        components,
        key=lambda item: (
            item["logical_path"].split("/")[0] if options["group_by_module"] else "",
            -degree.get(item["ref"], 0),
            natural_key(item["ref"]),
        ),
    )
    placements = []
    columns = max(1, min(4, int(len(ordered) ** 0.5) or 1))
    x_origins, y_origins = _layout_origins(ordered, columns, options)
    for index, component in enumerate(ordered):
        column = index % columns
        row = index // columns
        instance = expanded["instances"][component["logical_path"]]
        kind, part = resolver.resolve(instance["part"])
        source = resolver.source(kind, part)
        library_uuid = source.get("library_uuid")
        device_uuid = source.get("device_uuid")
        if not library_uuid or not device_uuid:
            return _error(
                "PLAN_INVALID",
                f"{component['ref']} has no reviewed EasyEDA device identity",
                designator=component["ref"],
                warnings=warnings,
            )
        placements.append(
            {
                "client_id": f"plan/{component['ref']}",
                "logical_path": component["logical_path"],
                "library_uuid": library_uuid,
                "device_uuid": device_uuid,
                "device_name": source.get("device_name"),
                "designator": component["ref"],
                "x": x_origins[column],
                "y": y_origins[row],
                "rotation": 0,
                "mirror": False,
            }
        )
    sheet, sheet_error = _sheet(spec, placements, options)
    if sheet_error:
        return sheet_error
    instance_by_ref = {}
    for component in components:
        instance = expanded["instances"][component["logical_path"]]
        kind, part = resolver.resolve(instance["part"])
        source = resolver.source(kind, part)
        review = (part or {}).get("review") or {}
        project_types = {
            str(pin.get("number")): pin.get("type")
            for pin in resolver.pins(kind, part)
        }
        raw_types = {
            str(number): value
            for number, value in (source.get("raw_pin_types") or {}).items()
        }
        authority = review.get("pin_type_authority")
        instance_by_ref[component["ref"]] = {
            "region": component["logical_path"].split("/", 1)[0]
            if "/" in component["logical_path"]
            else "root",
            "pin_types": raw_types if authority == "source_library" else project_types,
            "trusted": review.get("status") == "project_reviewed"
            and authority in {"source_library", "project_library"},
        }

    wires, labels, ports, flags, connection_intents = [], [], [], [], []
    for net in sorted(nets, key=lambda item: natural_key(item["name"])):
        nodes = sorted(net["nodes"], key=lambda node: (natural_key(node[0]), natural_key(node[1])))
        endpoints = [f"{ref}.#{pin}" for ref, pin in nodes]
        endpoint_details = [
            {
                "selector": f"{ref}.#{pin}",
                "region": instance_by_ref[ref]["region"],
                "pin_type": instance_by_ref[ref]["pin_types"].get(str(pin)),
                "pin_type_trusted": instance_by_ref[ref]["trusted"],
            }
            for ref, pin in nodes
        ]
        annotation_policy = options["net_annotation_policy"]
        net_origin = net.get("net_origin", "explicit")
        marker_kind = None
        marker_endpoints = []
        cross_region = len({item["region"] for item in endpoint_details}) > 1
        if annotation_policy == "sparse_named":
            strategy = "direct"
            if len(endpoints) >= 2:
                wires.append(
                    {
                        "net": net["name"],
                        "branches": [
                            {
                                "client_id": f"plan/{net['name']}/wire/{index}",
                                "start": endpoints[0],
                                "end": endpoint,
                                "waypoints": [],
                                "role": "direct",
                            }
                            for index, endpoint in enumerate(endpoints[1:])
                        ],
                    }
                )
            if net_origin == "explicit" and endpoints:
                connector_endpoints = [
                    endpoint
                    for endpoint in endpoints
                    if endpoint.split(".", 1)[0].upper().startswith("J")
                ]
                marker_endpoints = [connector_endpoints[0] if connector_endpoints else endpoints[0]]
                marker_kind = (
                    "flag" if net.get("kind") in {"power", "ground"} else "port"
                )
                marker = {
                    "client_id": f"plan/{net['name']}/{marker_kind}/0",
                    "net": net["name"],
                    "at": marker_endpoints[0],
                    "rotation": 0,
                    "mirror": False,
                }
                if marker_kind == "flag":
                    marker["identification"] = (
                        "Ground" if net.get("kind") == "ground" else "Power"
                    )
                    flags.append(marker)
                else:
                    marker["direction"] = "BI"
                    ports.append(marker)
        elif net.get("kind") in {"power", "ground"}:
            strategy = "flag"
        elif len(endpoints) >= 3 or cross_region:
            strategy = (
                "label"
                if options["net_annotation_policy"] == "legacy_selective"
                and options["high_fanout_primitive"] == "label"
                else "port"
            )
        elif len(endpoints) == 2:
            strategy = "direct"
            wires.append(
                {"net": net["name"], "branches": [{"client_id": f"plan/{net['name']}/wire/0", "start": endpoints[0], "end": endpoints[1], "waypoints": [], "role": "direct"}]}
            )
        elif len(endpoints) == 1:
            strategy = "port"
        else:
            strategy = "port"
        if annotation_policy == "every_endpoint":
            if net.get("kind") in {"power", "ground"}:
                identification = "Ground" if net.get("kind") == "ground" else "Power"
                flags.extend(
                    {
                        "client_id": f"plan/{net['name']}/flag/{index}",
                        "net": net["name"],
                        "at": endpoint,
                        "identification": identification,
                        "rotation": 0,
                        "mirror": False,
                    }
                    for index, endpoint in enumerate(endpoints)
                )
            else:
                ports.extend(
                    {
                        "client_id": f"plan/{net['name']}/port/{index}",
                        "net": net["name"],
                        "at": endpoint,
                        "direction": "BI",
                        "rotation": 0,
                        "mirror": False,
                    }
                for index, endpoint in enumerate(endpoints)
            )
        elif annotation_policy == "sparse_named":
            pass
        elif strategy == "flag":
            identification = "Ground" if net.get("kind") == "ground" else "Power"
            flags.extend(
                {
                    "client_id": f"plan/{net['name']}/flag/{index}",
                    "net": net["name"],
                    "at": endpoint,
                    "identification": identification,
                    "rotation": 0,
                    "mirror": False,
                }
                for index, endpoint in enumerate(endpoints)
            )
        elif strategy == "label":
            labels.extend(
                {
                    "client_id": f"plan/{net['name']}/label/{index}",
                    "net": net["name"],
                    "at": endpoint,
                    "rotation": 0,
                    "mirror": False,
                }
                for index, endpoint in enumerate(endpoints)
            )
        elif strategy == "port":
            ports.extend(
                {
                    "client_id": f"plan/{net['name']}/port/{index}",
                    "net": net["name"],
                    "at": endpoint,
                    "direction": "BI",
                    "rotation": 0,
                    "mirror": False,
                }
                for index, endpoint in enumerate(endpoints)
            )
        connection_intents.append(
            {
                "net": net["name"],
                "kind": net.get("kind"),
                "net_origin": net_origin,
                "strategy": strategy,
                "annotation_policy": annotation_policy,
                "marker_kind": marker_kind,
                "marker_endpoints": marker_endpoints,
                "endpoints": endpoint_details,
            }
        )
    topology = {
        "components": sorted(component["ref"] for component in components),
        "nets": {net["name"]: [[ref, pin] for ref, pin in sorted(net["nodes"])] for net in sorted(nets, key=lambda item: item["name"])},
    }
    topology_endpoints = sum(len(value) for value in topology["nets"].values())
    planned_marker_pairs = {
        (item["net"], item["at"])
        for collection in (labels, ports, flags)
        for item in collection
        if isinstance(item.get("at"), str)
    }
    required_marker_pairs = {
        (intent["net"], endpoint)
        for intent in connection_intents
        for endpoint in (
            [item["selector"] for item in intent["endpoints"]]
            if intent["annotation_policy"] == "every_endpoint"
            else intent.get("marker_endpoints", [])
            if intent["annotation_policy"] == "sparse_named"
            else []
        )
    }
    missing_markers = [
        {"net": net, "endpoint": endpoint}
        for net, endpoint in sorted(
            required_marker_pairs - planned_marker_pairs,
            key=lambda value: (natural_key(value[0]), natural_key(value[1])),
        )
    ]
    plan = {
        "format": "schematic-plan/v0.2",
        "phase": "logical",
        "options": options,
        "placements": placements,
        "wires": wires,
        "labels": labels,
        "ports": ports,
        "flags": flags,
        "no_connects": [
            {"designator": expanded.get("reference_map", {}).get(path, path), "pin_selectors": sorted(instance.get("no_connects") or [], key=natural_key)}
            for path, instance in sorted(expanded.get("instances", {}).items())
            if instance.get("no_connects")
        ],
        "connection_intents": connection_intents,
        "visual": {
            "expected_endpoints": topology_endpoints,
            "resolved_endpoints": 0,
            "marker_endpoints": len(planned_marker_pairs),
            "direct_endpoints": sum(
                len(intent["endpoints"])
                for intent in connection_intents
                if intent["strategy"] == "direct"
            ),
            "visible_net_endpoints": len(required_marker_pairs & planned_marker_pairs),
            "missing_net_markers": missing_markers,
            "fallbacks": [],
        },
        "sheet": sheet,
        "topology": topology,
        "topology_hash": _hash(topology),
    }
    plan["plan_hash"] = _hash(plan)
    return {"ok": True, "errors": [], "warnings": warnings, "plan": plan}


def diff_plan(plan: dict, state: dict) -> dict:
    if plan.get("format") not in {"schematic-plan/v0.1", "schematic-plan/v0.2"}:
        return _error("PLAN_INVALID", "unsupported or missing schematic plan format")
    current = {item.get("designator"): item for item in state.get("components", [])}
    create, reuse, move, conflicts = [], [], [], []
    for wanted in plan.get("placements", []):
        found = current.get(wanted.get("designator"))
        if not found:
            create.append(wanted)
            continue
        identity = found.get("component") or {}
        same_library = identity.get("libraryUuid") == wanted.get("library_uuid")
        same_device = identity.get("uuid") == wanted.get("device_uuid") or (
            wanted.get("device_name") and identity.get("name") == wanted.get("device_name")
        )
        if not (same_library and same_device):
            conflicts.append({"designator": wanted.get("designator"), "reason": "device identity differs", "current": identity})
        elif (found.get("x"), found.get("y"), found.get("rotation"), found.get("mirror")) != (
            wanted.get("x"), wanted.get("y"), wanted.get("rotation"), wanted.get("mirror")
        ):
            move.append(wanted)
        else:
            reuse.append(wanted.get("designator"))
    planned_refs = {item.get("designator") for item in plan.get("placements", [])}
    extra = [item for ref, item in sorted(current.items()) if ref not in planned_refs]
    if plan.get("format") == "schematic-plan/v0.2" and plan.get("phase") != "resolved":
        return {
            "ok": not conflicts,
            "create": create,
            "reuse": reuse,
            "move": move,
            "conflicts": conflicts,
            "extra": extra,
            "requires_resolution": True,
            "wiring": None,
            "expected": {
                "components": len(plan.get("topology", {}).get("components", [])),
                "nets": len(plan.get("topology", {}).get("nets", {})),
                "nodes": sum(len(value) for value in plan.get("topology", {}).get("nets", {}).values()),
            },
        }
    pins = {
        f"{component.get('designator')}.#{pin.get('number')}": (pin.get("x"), pin.get("y"))
        for component in state.get("components", []) for pin in component.get("pins", [])
    }
    def point(value):
        return pins.get(value) if isinstance(value, str) else (value.get("x"), value.get("y"))
    if plan.get("format") == "schematic-plan/v0.2":
        wanted_by_net = {
            wire.get("net"): {
                "net": wire.get("net"),
                "net_origin": wire.get("net_origin", "explicit"),
                "branches": list(wire.get("branches", [])),
            }
            for wire in plan.get("wires", [])
            if wire.get("branches")
        }
        actual_topology = (
            parse_protel2_netlist(state["netlist"]).get("nets", {})
            if state.get("netlist")
            else {}
        )
        expected_topology = plan.get("topology", {}).get("nets", {})
        used_actual_nets = set()
        present_nets = set()
        for net, wanted in wanted_by_net.items():
            expected_nodes = {
                tuple(node) for node in expected_topology.get(net, [])
            }
            if wanted["net_origin"] == "explicit":
                if set(actual_topology.get(net, [])) == expected_nodes:
                    present_nets.add(net)
                    used_actual_nets.add(net)
                continue
            matches = [
                actual_name
                for actual_name, actual_nodes in actual_topology.items()
                if actual_name not in used_actual_nets
                and set(actual_nodes) == expected_nodes
            ]
            if matches:
                actual_name = sorted(matches, key=natural_key)[0]
                present_nets.add(net)
                used_actual_nets.add(actual_name)
        missing_wires = [
            wanted_by_net[net]
            for net in sorted(wanted_by_net, key=natural_key)
            if net not in present_nets
        ]
        extra_wires = [
            wire
            for wire in state.get("wires", [])
            if wire.get("net")
            and wire.get("net") not in used_actual_nets
            and wire.get("net") not in wanted_by_net
        ]
    else:
        wanted_wires = []
        for wire in plan.get("wires", []):
            for branch in wire.get("branches", []):
                wanted_wires.append((wire.get("net"), frozenset((point(branch.get("start")), point(branch.get("end")))), branch))
        actual_wires = []
        for wire in state.get("wires", []):
            points = wire.get("points") or []
            if len(points) >= 2:
                actual_wires.append((wire.get("net"), frozenset(((points[0]["x"], points[0]["y"]), (points[-1]["x"], points[-1]["y"]))), wire))
        missing_wires = [{"net": net, "branches": [branch]} for net, ends, branch in wanted_wires if not any(net == other_net and ends == other_ends for other_net, other_ends, _ in actual_wires)]
        extra_wires = [wire for net, ends, wire in actual_wires if not any(net == other_net and ends == other_ends for other_net, other_ends, _ in wanted_wires)]

    marker_diff = {}
    for kind in ("labels", "ports", "flags"):
        wanted = sorted(plan.get(kind, []), key=lambda item: (natural_key(item.get("net")), natural_key(item.get("anchor")), item.get("client_id") or ""))
        actual = sorted(state.get(kind, []), key=lambda item: item.get("id") or "")
        used, created, replaced, unchanged = set(), [], [], []
        singular = kind[:-1]
        pending = []
        for item in wanted:
            location = point(item.get("at"))
            exact = next((
                row for row in actual
                if row.get("id") not in used
                and row.get("net") == item.get("net")
                and abs(row.get("x", float("inf")) - location[0]) <= 1e-6
                and abs(row.get("y", float("inf")) - location[1]) <= 1e-6
                and row.get("rotation") == item.get("rotation", 0)
                and (kind != "ports" or row.get("direction_status") != "readback" or row.get("direction") == item.get("direction"))
                and (kind != "flags" or row.get("identification_status") != "readback" or row.get("identification") == item.get("identification"))
            ), None)
            if exact:
                used.add(exact.get("id"))
                unchanged.append(exact.get("id"))
            else:
                pending.append((item, location))
        for item, location in pending:
            same_net = [row for row in actual if row.get("id") not in used and row.get("net") == item.get("net")]
            if same_net:
                found = min(same_net, key=lambda row: (abs(row.get("x", 0) - location[0]) + abs(row.get("y", 0) - location[1]), row.get("id") or ""))
                used.add(found.get("id"))
                replacement = {**item, "kind": singular, "at": {"x": location[0], "y": location[1]}}
                replaced.append({"op": "replace", "kind": singular, "id": found.get("id"), "replacement": replacement})
            else:
                created.append(item)
        marker_diff[kind] = {
            "create": created,
            "replace": replaced,
            "delete": [row for row in actual if row.get("id") not in used],
            "unchanged": unchanged,
        }
    wanted_nc = {(item["designator"], pin) for item in plan.get("no_connects", []) for pin in item.get("pin_selectors", [])}
    actual_nc = {(item.get("designator"), item.get("pin")) for item in state.get("no_connects", [])}
    no_connects = {
        "create": [{"designator": ref, "pin": pin} for ref, pin in sorted(wanted_nc - actual_nc, key=lambda value: (natural_key(value[0]), natural_key(value[1])))],
        "delete": [{"designator": ref, "pin": pin} for ref, pin in sorted(actual_nc - wanted_nc, key=lambda value: (natural_key(value[0]), natural_key(value[1])))],
    }
    return {
        "ok": not conflicts,
        "create": create,
        "reuse": reuse,
        "move": move,
        "conflicts": conflicts,
        "extra": extra,
        "wiring": {"wires": {"create": missing_wires, "delete": extra_wires}, **marker_diff, "no_connects": no_connects},
        "expected": {
            "components": len(plan.get("topology", {}).get("components", [])),
            "nets": len(plan.get("topology", {}).get("nets", {})),
            "nodes": sum(len(value) for value in plan.get("topology", {}).get("nets", {}).values()),
        },
    }


def compare_topology(
    expected_text: str,
    actual_text: str,
    generated_nets: set[str] | None = None,
) -> dict:
    expected = parse_protel2_netlist(expected_text)
    actual = parse_protel2_netlist(actual_text)
    generated_nets = set(generated_nets or [])
    expected_components, actual_components = set(expected["components"]), set(actual["components"])
    missing_components = sorted(expected_components - actual_components, key=natural_key)
    extra_components = sorted(actual_components - expected_components, key=natural_key)
    missing, extra, changed = {}, {}, []
    generated_net_map = {}
    used_actual = set()
    for name in sorted(set(expected["nets"]) - generated_nets, key=natural_key):
        left, right = set(expected["nets"].get(name, [])), set(actual["nets"].get(name, []))
        if name in actual["nets"]:
            used_actual.add(name)
        if left - right:
            missing[name] = [list(node) for node in sorted(left - right)]
        if right - left:
            extra[name] = [list(node) for node in sorted(right - left)]
        if left != right:
            changed.append(name)
    for name in sorted(generated_nets & set(expected["nets"]), key=natural_key):
        left = set(expected["nets"].get(name, []))
        matches = [
            actual_name
            for actual_name, nodes in actual["nets"].items()
            if actual_name not in used_actual and set(nodes) == left
        ]
        if matches:
            actual_name = sorted(matches, key=natural_key)[0]
            used_actual.add(actual_name)
            generated_net_map[name] = actual_name
        else:
            missing[name] = [list(node) for node in sorted(left)]
            changed.append(name)
    for name in sorted(set(actual["nets"]) - used_actual, key=natural_key):
        right = set(actual["nets"].get(name, []))
        extra[name] = [list(node) for node in sorted(right)]
        changed.append(name)
    return {
        "ok": not (missing_components or extra_components or missing or extra),
        "missing_components": missing_components,
        "extra_components": extra_components,
        "missing": missing,
        "extra": extra,
        "changed": changed,
        "generated_net_map": generated_net_map,
        "counts": {
            "expected_components": len(expected_components),
            "actual_components": len(actual_components),
            "expected_nets": len(expected["nets"]),
            "actual_nets": len(actual["nets"]),
            "expected_nodes": sum(len(nodes) for nodes in expected["nets"].values()),
            "actual_nodes": sum(len(nodes) for nodes in actual["nets"].values()),
        },
    }


def expected_netlist(spec_yaml: str, base_dir: str | None = None) -> tuple[str | None, dict | None]:
    spec = _load_spec(spec_yaml)
    if not spec:
        return None, _error("PLAN_INVALID", "BoardSpec is not a mapping")
    resolver, resolver_errors = _resolver(spec_yaml, base_dir)
    if resolver_errors:
        return None, _error("PLAN_INVALID", "part library resolution failed", errors=resolver_errors)
    expanded, errors, warnings = boardspec.analyze(spec, resolver)
    if errors:
        return None, _error("PLAN_INVALID", "BoardSpec validation failed", errors=errors, warnings=warnings)
    return render_protel2_netlist(expanded, resolver), None


def expected_generated_nets(
    spec_yaml: str, base_dir: str | None = None
) -> tuple[set[str] | None, dict | None]:
    spec = _load_spec(spec_yaml)
    if not spec:
        return None, _error("PLAN_INVALID", "BoardSpec is not a mapping")
    resolver, resolver_errors = _resolver(spec_yaml, base_dir)
    if resolver_errors:
        return None, _error(
            "PLAN_INVALID", "part library resolution failed", errors=resolver_errors
        )
    expanded, errors, warnings = boardspec.analyze(spec, resolver)
    if errors:
        return None, _error(
            "PLAN_INVALID",
            "BoardSpec validation failed",
            errors=errors,
            warnings=warnings,
        )
    _, nets = boardspec.build_flat(expanded, resolver)
    return {
        net["name"]
        for net in nets
        if net.get("net_origin", "explicit") == "generated"
    }, None
