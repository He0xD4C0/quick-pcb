"""Pure deterministic planning, diffing and topology comparison."""

from __future__ import annotations

import hashlib
import json
import math
import os

import boardspec
from boardspec.exporters import parse_protel2_netlist, render_protel2_netlist

from . import tools
from .schematic_codec import natural_key, require_grid


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


def _resolver(yaml_text: str, base_dir: str | None = None):
    spec = tools._load_spec(yaml_text)
    if not spec:
        return None, [{"code": "SCHEMA_INVALID", "path": "/", "message": "specification is not a mapping"}]
    resolver, errors = boardspec.build_resolver(spec, base_dir or os.getcwd(), [])
    return resolver, errors


def build_plan(spec_yaml: str, options: dict | None = None) -> dict:
    options = {
        "page_policy": "single_page",
        "wiring_policy": "hybrid",
        "grid_mil": 100,
        "column_gap_mil": 1000,
        "row_gap_mil": 600,
        "group_by_module": True,
        "high_fanout_primitive": "auto",
        "readability_policy": "standard_hybrid",
        "stub_lengths_mil": [200, 300, 400, 500, 600],
        "marker_clearance_mil": 100,
        "cross_region_distance_mil": 2000,
        "use_trusted_pin_directions": True,
        "preserve_existing_placements": False,
        "measured_geometry": {},
        "base_dir": None,
        **(options or {}),
    }
    spec = tools._load_spec(spec_yaml)
    if not spec:
        return _error("PLAN_INVALID", "BoardSpec is not a mapping")
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
        cross_region = len({item["region"] for item in endpoint_details}) > 1
        if net.get("kind") in {"power", "ground"}:
            strategy = "flag"
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
        elif len(endpoints) >= 3 or cross_region:
            strategy = "port"
            if options["high_fanout_primitive"] == "label":
                strategy = "label"
                labels.extend(
                    {"client_id": f"plan/{net['name']}/label/{index}", "net": net["name"], "at": endpoint, "rotation": 0, "mirror": False}
                    for index, endpoint in enumerate(endpoints)
                )
            else:
                ports.extend(
                    {"client_id": f"plan/{net['name']}/port/{index}", "net": net["name"], "at": endpoint,
                     "direction": "BI", "rotation": 0, "mirror": False}
                    for index, endpoint in enumerate(endpoints)
                )
        elif len(endpoints) == 2:
            strategy = "direct"
            wires.append(
                {"net": net["name"], "branches": [{"client_id": f"plan/{net['name']}/wire/0", "start": endpoints[0], "end": endpoints[1], "waypoints": [], "role": "direct"}]}
            )
        elif len(endpoints) == 1:
            strategy = "port"
            marker = {"client_id": f"plan/{net['name']}/label/0", "net": net["name"], "at": endpoints[0], "rotation": 0, "mirror": False}
            if options["high_fanout_primitive"] != "label":
                ports.append({**marker, "client_id": f"plan/{net['name']}/port/0", "direction": "BI"})
            else:
                labels.append(marker)
        else:
            strategy = "port"
        connection_intents.append(
            {
                "net": net["name"],
                "kind": net.get("kind"),
                "strategy": strategy,
                "endpoints": endpoint_details,
            }
        )
    topology = {
        "components": sorted(component["ref"] for component in components),
        "nets": {net["name"]: [[ref, pin] for ref, pin in sorted(net["nodes"])] for net in sorted(nets, key=lambda item: item["name"])},
    }
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
        "visual": None,
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
                and (row.get("x"), row.get("y")) == location
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


def compare_topology(expected_text: str, actual_text: str) -> dict:
    expected = parse_protel2_netlist(expected_text)
    actual = parse_protel2_netlist(actual_text)
    expected_components, actual_components = set(expected["components"]), set(actual["components"])
    missing_components = sorted(expected_components - actual_components, key=natural_key)
    extra_components = sorted(actual_components - expected_components, key=natural_key)
    missing, extra, changed = {}, {}, []
    for name in sorted(set(expected["nets"]) | set(actual["nets"]), key=natural_key):
        left, right = set(expected["nets"].get(name, [])), set(actual["nets"].get(name, []))
        if left - right:
            missing[name] = [list(node) for node in sorted(left - right)]
        if right - left:
            extra[name] = [list(node) for node in sorted(right - left)]
        if left != right:
            changed.append(name)
    return {
        "ok": not (missing_components or extra_components or missing or extra),
        "missing_components": missing_components,
        "extra_components": extra_components,
        "missing": missing,
        "extra": extra,
        "changed": changed,
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
    spec = tools._load_spec(spec_yaml)
    if not spec:
        return None, _error("PLAN_INVALID", "BoardSpec is not a mapping")
    resolver, resolver_errors = _resolver(spec_yaml, base_dir)
    if resolver_errors:
        return None, _error("PLAN_INVALID", "part library resolution failed", errors=resolver_errors)
    expanded, errors, warnings = boardspec.analyze(spec, resolver)
    if errors:
        return None, _error("PLAN_INVALID", "BoardSpec validation failed", errors=errors, warnings=warnings)
    return render_protel2_netlist(expanded, resolver), None
