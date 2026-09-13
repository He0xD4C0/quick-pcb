"""Core analysis: schema validation, module expansion, and conservative ERC.

Ported from the reference ``skills/board-spec/scripts/_bspec.py`` implementation
into an installable package. The semantics are unchanged: schema validation,
hierarchical module flattening (``PARENT/CHILD``), endpoint resolution, and
conservative electrical rule checks.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy

import jsonschema
from .diag import diag
from .part_db import build_resolver, split_part
from .schema import load_schema
from .yaml_io import YAMLError, format_yaml_error, load_yaml_file

_ELECTRICAL_OUTPUT_TYPES = ("output", "power_out", "tri_state")
_SIGNAL_PIN_TYPES = ("input", "bidirectional", "tri_state")

_ENDPOINT_RE = re.compile(
    r"^(?P<inst>[A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)*)\.(?P<pin>.*)$"
)
_PHYSICAL_REF_RE = re.compile(r"^[A-Za-z]+[1-9][0-9]*$")


def _dedupe(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def load_yaml(path):
    return load_yaml_file(path)


def parse_endpoint(ep):
    """Split an endpoint string into ``(instance_path, pin_or_port_token)``."""
    m = _ENDPOINT_RE.match(ep)
    if not m:
        return None
    return m.group("inst"), m.group("pin")


def resolve_pins(pins, token):
    """Resolve a pin/port token against a list of pin dicts.

    ``#NUMBER`` selects one physical pin; a bare name selects every physical pin
    sharing that logical name.
    """
    if not token:
        return []
    if token.startswith("#"):
        num = token[1:]
        return [p for p in pins if str(p.get("number")) == num]
    return [p for p in pins if p.get("name") == token]


def pin_name_hint(pins, limit=12):
    names = _dedupe(str(p.get("name")) for p in pins)
    if not names:
        return "no pins available"
    shown = names if len(names) <= limit else names[:limit] + ["..."]
    return "available pins: " + ", ".join(shown)


def _subst(s, params):
    def repl(m):
        name = m.group(1)
        return str(params[name]) if name in params else m.group(0)

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, s)


def _module_params(part, inst, path, warnings):
    declared = part.get("parameters", {}) or {}
    params = {}
    for name, spec in declared.items():
        params[name] = spec.get("default")
    for name, value in (inst.get("parameters") or {}).items():
        if name not in declared:
            warnings.append(
                diag(
                    "UNKNOWN_PARAMETER",
                    f"/instances/{path}",
                    f"parameter '{name}' is not declared by module '{inst.get('part')}'",
                )
            )
        params[name] = value
    return params


def _expand_endpoints(endpoints, port_bindings):
    """Replace module-port endpoints with their mapped hierarchical endpoints."""
    out = []
    for ep in endpoints:
        parsed = parse_endpoint(ep)
        if parsed and parsed in port_bindings:
            out.extend(_expand_endpoints(port_bindings[parsed], port_bindings))
        else:
            out.append(ep)
    return _dedupe(out)


def _validate_module_nets(part, module_key, resolver, errors):
    items = part.get("items", {}) or {}
    for i, net in enumerate(part.get("nets", []) or []):
        for j, ep in enumerate(net.get("endpoints", []) or []):
            parsed = parse_endpoint(ep)
            base = f"/definitions/{module_key}/nets/{i}/endpoints/{j}"
            if not parsed:
                errors.append(diag("SCHEMA_INVALID", base, f"invalid endpoint '{ep}'"))
                continue
            child, token = parsed
            if child not in items:
                errors.append(
                    diag(
                        "UNKNOWN_INSTANCE",
                        base,
                        f"instance '{child}' not found in module '{module_key}'",
                    )
                )
                continue
            ckind, cpart = resolver.resolve(items[child].get("part", ""))
            if ckind == "module":
                ports = cpart.get("ports", {}) or {}
                if token not in ports:
                    errors.append(
                        diag(
                            "UNKNOWN_PIN",
                            base,
                            f"port '{token}' not found on module '{child}'",
                            hint="available ports: " + ", ".join(sorted(ports)),
                        )
                    )
            elif ckind in ("physical", "library"):
                pins = resolver.pins(ckind, cpart)
                if not resolve_pins(pins, token):
                    errors.append(
                        diag("UNKNOWN_PIN", base, f"'{ep}' not found", hint=pin_name_hint(pins))
                    )
            else:
                errors.append(
                    diag("UNKNOWN_PART", base, f"part '{items[child].get('part')}' not found")
                )


def allocate_references(flat_instances, resolver, errors):
    """Allocate deterministic EDA-safe references for flattened instances."""
    reference_map = {}
    used = set()

    for path in sorted(name for name in flat_instances if "/" not in name):
        folded = path.upper()
        if not _PHYSICAL_REF_RE.fullmatch(path):
            errors.append(
                diag(
                    "INVALID_REFERENCE",
                    f"/instances/{path}",
                    f"top-level physical instance '{path}' is not an EDA reference",
                    "Use letters followed by a positive integer, for example U1 or C3.",
                )
            )
        elif folded in used:
            errors.append(
                diag(
                    "REFERENCE_COLLISION",
                    f"/instances/{path}",
                    f"physical reference '{path}' collides case-insensitively",
                )
            )
        reference_map[path] = path
        used.add(folded)

    for path in sorted(name for name in flat_instances if "/" in name):
        inst = flat_instances[path]
        kind, part = resolver.resolve(inst.get("part", ""))
        prefix = resolver.reference_prefix(kind, part)
        if not prefix or not re.fullmatch(r"[A-Za-z]+", str(prefix)):
            errors.append(
                diag(
                    "REFERENCE_PREFIX_UNRESOLVED",
                    f"/instances/{path}",
                    f"instance '{path}' has no valid reference_prefix",
                    "Snapshot the source library designator, such as R?, as reference_prefix: R.",
                )
            )
            reference_map[path] = path
            continue
        number = 1
        while f"{prefix}{number}".upper() in used:
            number += 1
        reference = f"{prefix}{number}"
        reference_map[path] = reference
        used.add(reference.upper())

    return reference_map


def analyze(spec, resolver):
    """Validate a spec and return ``(expanded_spec, errors, warnings)``.

    ``expanded_spec`` is ``None`` when schema validation fails.
    """
    errors = []
    warnings = []

    validator = jsonschema.Draft202012Validator(load_schema())
    schema_errors = list(validator.iter_errors(spec))
    if schema_errors:
        for e in schema_errors:
            parts = [str(p) for p in e.absolute_path]
            path = "/" + "/".join(parts) if parts else "/"
            errors.append(diag("SCHEMA_INVALID", path, e.message))
        return None, errors, warnings

    definitions = spec.get("definitions", {}) or {}
    instances = spec.get("instances", {}) or {}
    connections = spec.get("connections", []) or []

    flat_instances = {}
    port_bindings = {}
    module_ports = {}
    module_paths = set()
    standalone_nets = []
    visited = []

    def substitute(inst, params):
        new = deepcopy(inst)
        for key in ("value", "footprint"):
            if isinstance(new.get(key), str):
                new[key] = _subst(new[key], params)
        for key in ("parameters", "properties"):
            if isinstance(new.get(key), dict):
                new[key] = {
                    k: (_subst(v, params) if isinstance(v, str) else v)
                    for k, v in new[key].items()
                }
        return new

    def walk(parent, items, scope):
        for name, inst in items.items():
            path = f"{parent}/{name}" if parent else name
            inst = substitute(inst, scope)
            part_ref = inst.get("part", "")
            kind, part = resolver.resolve(part_ref)
            if kind is None:
                errors.append(
                    diag("UNKNOWN_PART", f"/instances/{path}", f"part '{part_ref}' not found")
                )
                continue
            if kind == "module":
                if inst.get("no_connects"):
                    errors.append(
                        diag(
                            "MODULE_NO_CONNECT_UNSUPPORTED",
                            f"/instances/{path}/no_connects",
                            "no_connects may only be declared on physical instances",
                        )
                    )
                module_paths.add(path)
                ports = part.get("ports", {}) or {}
                module_ports[path] = set(ports)
                params = _module_params(part, inst, path, warnings)
                net_by_name = {n["net"]: n for n in (part.get("nets", []) or [])}
                pm = part.get("port_map", {}) or {}
                for port in ports:
                    if port not in pm:
                        errors.append(
                            diag(
                                "PORT_MAP_INVALID",
                                f"/definitions/{part_ref}/port_map",
                                f"port '{port}' of module '{part_ref}' has no mapping",
                            )
                        )
                    elif pm[port] not in net_by_name:
                        errors.append(
                            diag(
                                "PORT_MAP_INVALID",
                                f"/definitions/{part_ref}/port_map/{port}",
                                f"mapped net '{pm[port]}' not found in module '{part_ref}'",
                            )
                        )
                for port in pm:
                    if port not in ports:
                        warnings.append(
                            diag(
                                "PORT_MAP_INVALID",
                                f"/definitions/{part_ref}/port_map/{port}",
                                f"port_map entry '{port}' is not a declared port",
                            )
                        )
                for port, netname in pm.items():
                    net = net_by_name.get(netname)
                    if net is not None:
                        port_bindings[(path, port)] = [
                            f"{path}/{ep}" for ep in (net.get("endpoints", []) or [])
                        ]
                _validate_module_nets(part, part_ref, resolver, errors)
                mapped = set(pm.values())
                for net in (part.get("nets", []) or []):
                    if net["net"] not in mapped:
                        standalone_nets.append(
                            {
                                "net": f"{path}/{net['net']}",
                                "endpoints": [
                                    f"{path}/{ep}" for ep in (net.get("endpoints", []) or [])
                                ],
                            }
                        )
                if part_ref in visited:
                    errors.append(
                        diag(
                            "MODULE_CYCLE",
                            f"/definitions/{part_ref}",
                            f"module '{part_ref}' is recursive",
                        )
                    )
                else:
                    visited.append(part_ref)
                    walk(path, part.get("items", {}) or {}, params)
                    visited.pop()
            else:
                flat_instances[path] = inst

    walk(None, instances, {})

    flat_connections = []
    for conn in connections:
        new_conn = dict(conn)
        new_conn["endpoints"] = _expand_endpoints(
            conn.get("endpoints", []) or [], port_bindings
        )
        flat_connections.append(new_conn)
    for net in standalone_nets:
        net["endpoints"] = _expand_endpoints(net["endpoints"], port_bindings)
        flat_connections.append(net)

    net_pins = {}
    pin_owner = {}
    seen_nets = set()
    original_count = len(connections)
    for idx, conn in enumerate(flat_connections):
        net = conn.get("net")
        is_original = idx < original_count
        if net in seen_nets:
            errors.append(
                diag(
                    "DUPLICATE_NET",
                    f"/connections/{idx}" if is_original else "/definitions",
                    f"net '{net}' is defined more than once",
                )
            )
        seen_nets.add(net)
        for j, ep in enumerate(conn.get("endpoints", []) or []):
            base = (
                f"/connections/{idx}/endpoints/{j}"
                if is_original
                else f"/definitions/{net}/endpoints/{j}"
            )
            parsed = parse_endpoint(ep)
            if not parsed:
                errors.append(diag("SCHEMA_INVALID", base, f"invalid endpoint '{ep}'"))
                continue
            inst, token = parsed
            if inst in module_paths:
                ports = module_ports.get(inst, set())
                errors.append(
                    diag(
                        "UNKNOWN_PIN",
                        base,
                        f"'{token}' is not a port of module '{inst}'",
                        hint="available ports: " + ", ".join(sorted(ports)),
                    )
                )
                continue
            leaf = flat_instances.get(inst)
            if leaf is None:
                errors.append(diag("UNKNOWN_INSTANCE", base, f"instance '{inst}' not found"))
                continue
            kind, part = resolver.resolve(leaf.get("part", ""))
            if kind is None:
                errors.append(
                    diag("UNKNOWN_PART", base, f"part '{leaf.get('part')}' not found")
                )
                continue
            pins = resolver.pins(kind, part)
            matched = resolve_pins(pins, token)
            if not matched:
                errors.append(
                    diag("UNKNOWN_PIN", base, f"'{ep}' not found", hint=pin_name_hint(pins))
                )
                continue
            for p in matched:
                net_pins.setdefault(net, []).append((inst, p))
                key = (inst, str(p.get("number")))
                if key in pin_owner and pin_owner[key] != net:
                    errors.append(
                        diag(
                            "ENDPOINT_MULTIPLE_NETS",
                            base,
                            f"pin {inst}.{p.get('number')} is connected to both "
                            f"'{pin_owner[key]}' and '{net}'",
                        )
                    )
                pin_owner[key] = net

    net_kind = {}
    for conn in flat_connections:
        net_kind.setdefault(conn.get("net"), conn.get("kind"))

    def ptype(p):
        return p.get("type", "unspecified")

    no_connect_pins = set()
    for name, leaf in flat_instances.items():
        kind, part = resolver.resolve(leaf.get("part", ""))
        pins = resolver.pins(kind, part)
        for index, token in enumerate(leaf.get("no_connects", []) or []):
            matched = resolve_pins(pins, token)
            path = f"/instances/{name}/no_connects/{index}"
            if not matched:
                errors.append(
                    diag(
                        "UNKNOWN_PIN",
                        path,
                        f"no-connect pin '{name}.{token}' was not found",
                        hint=pin_name_hint(pins),
                    )
                )
                continue
            pin = matched[0]
            key = (name, str(pin.get("number")))
            if key in pin_owner:
                errors.append(
                    diag(
                        "PIN_CONNECTED_AND_NO_CONNECT",
                        path,
                        f"pin {name}.{pin.get('number')} is connected to "
                        f"'{pin_owner[key]}' and marked no-connect",
                    )
                )
            no_connect_pins.add(key)

    unspecified_connected = set()
    for net, pins in net_pins.items():
        for inst, pin in pins:
            key = (inst, str(pin.get("number")))
            if ptype(pin) == "unspecified" and key not in unspecified_connected:
                errors.append(
                    diag(
                        "UNSPECIFIED_PIN_CONNECTED",
                        f"/connections/{net}",
                        f"connected pin {inst}.{pin.get('number')} ({pin.get('name')}) "
                        "has an unreviewed electrical type",
                        "Review the project-library symbol and set an explicit BoardSpec type.",
                    )
                )
                unspecified_connected.add(key)

    # Resolvable connection conflicts.
    for net, pins in net_pins.items():
        drivers = [(inst, p) for inst, p in pins if ptype(p) in _ELECTRICAL_OUTPUT_TYPES]
        if len(drivers) > 1:
            detail = ", ".join(f"{i}.{p.get('number')}" for i, p in drivers)
            errors.append(
                diag(
                    "OUTPUT_CONFLICT",
                    f"/connections/{net}",
                    f"net '{net}' has multiple output drivers: {detail}",
                )
            )
        if net_kind.get(net) == "ground":
            for inst, p in pins:
                if ptype(p) in ("power_out", "output"):
                    errors.append(
                        diag(
                            "POWER_SHORT_TO_GROUND",
                            f"/connections/{net}",
                            f"ground net '{net}' is driven by {inst}.{p.get('number')} "
                            f"({p.get('name')})",
                        )
                    )

    inst_category = {}
    for name, leaf in flat_instances.items():
        kind, part = resolver.resolve(leaf.get("part", ""))
        inst_category[name] = (
            part.get("category") if kind in ("library", "physical") and part else None
        )

    # Heuristic warnings.
    for net, kind in net_kind.items():
        if kind != "power":
            continue
        pins = net_pins.get(net, [])
        has_power_in = any(ptype(p) == "power_in" for _, p in pins)
        has_cap = any(inst_category.get(inst) == "capacitor" for inst, _ in pins)
        if has_power_in and not has_cap:
            warnings.append(
                diag(
                    "MISSING_DECOUPLING",
                    f"/connections/{net}",
                    f"power net '{net}' has no decoupling capacitor",
                )
            )

    for net, pins in net_pins.items():
        has_oc = any(ptype(p) in ("open_collector", "open_emitter") for _, p in pins)
        has_r = any(inst_category.get(inst) == "resistor" for inst, _ in pins)
        if has_oc and not has_r:
            warnings.append(
                diag(
                    "MISSING_PULLUP",
                    f"/connections/{net}",
                    f"net '{net}' has an open-collector/open-emitter output with no pull-up",
                )
            )

    for name, leaf in flat_instances.items():
        if leaf.get("dnp"):
            continue
        kind, part = resolver.resolve(leaf.get("part", ""))
        reviewed = (
            kind == "physical"
            and (part.get("review") or {}).get("status") == "project_reviewed"
        )
        for p in resolver.pins(kind, part):
            key = (name, str(p.get("number")))
            if key in no_connect_pins:
                continue
            if ptype(p) == "power_in" and key not in pin_owner:
                errors.append(
                    diag(
                        "POWER_INPUT_UNCONNECTED",
                        f"/instances/{name}",
                        f"power pin {name}.{p.get('number')} ({p.get('name')}) is not connected",
                    )
                )
            if reviewed and key not in pin_owner and ptype(p) != "power_in":
                errors.append(
                    diag(
                        "UNCONNECTED_PIN",
                        f"/instances/{name}",
                        f"reviewed pin {name}.{p.get('number')} ({p.get('name')}) is neither "
                        "connected nor marked no-connect",
                    )
                )
            elif ptype(p) in _SIGNAL_PIN_TYPES and key not in pin_owner:
                warnings.append(
                    diag(
                        "UNCONNECTED_PIN",
                        f"/instances/{name}",
                        f"pin {name}.{p.get('number')} ({p.get('name')}) is not connected",
                    )
                )

    incomplete = set()
    for leaf in flat_instances.values():
        kind, part = resolver.resolve(leaf.get("part", ""))
        if kind == "library" and part and part.get("complete") is False:
            incomplete.add(leaf.get("part"))
    for pid in sorted(incomplete):
        warnings.append(
            diag(
                "INCOMPLETE_PART_DATA",
                "/instances",
                f"part '{pid}' has incomplete or unverified data",
            )
        )

    for name in sorted(flat_instances):
        leaf = flat_instances[name]
        if leaf.get("dnp"):
            continue
        kind, part = resolver.resolve(leaf.get("part", ""))
        fp = leaf.get("footprint") or resolver.footprint(kind, part)
        if not fp:
            warnings.append(
                diag(
                    "FOOTPRINT_UNCONFIRMED",
                    f"/instances/{name}",
                    f"instance '{name}' has no footprint",
                )
            )

    reference_map = allocate_references(flat_instances, resolver, errors)
    expanded = {
        "spec": "board-spec/v0.1",
        "project": spec.get("project", {}),
        "libraries": spec.get("libraries", []) or [],
        "definitions": {k: v for k, v in definitions.items() if v.get("kind") != "module"},
        "instances": flat_instances,
        "reference_map": reference_map,
        "connections": flat_connections,
        "constraints": spec.get("constraints", []) or [],
        "outputs": spec.get("outputs", []) or [],
    }
    return expanded, errors, warnings


def process(spec_path, extra_dbs=None):
    """Load a spec, build its resolver, and validate it.

    Returns ``(spec, expanded, resolver, errors, warnings)``.
    """
    extra_dbs = extra_dbs or []
    try:
        spec = load_yaml(spec_path)
    except YAMLError as exc:
        return (
            None,
            None,
            None,
            [
                diag(
                    "SCHEMA_INVALID",
                    "/",
                    format_yaml_error(exc),
                    "Fix the YAML syntax and retry validation.",
                )
            ],
            [],
        )
    if not isinstance(spec, dict):
        return (
            spec,
            None,
            None,
            [diag("SCHEMA_INVALID", "/", "specification is not a mapping")],
            [],
        )
    base_dir = os.path.dirname(os.path.abspath(spec_path))
    resolver, lib_errors = build_resolver(spec, base_dir, extra_dbs)
    expanded, errors, warnings = analyze(spec, resolver)
    return spec, expanded, resolver, lib_errors + errors, warnings


def expand(spec, resolver):
    """Return the expanded spec and diagnostics for an already-loaded spec dict."""
    expanded, errors, warnings = analyze(spec, resolver)
    return expanded, errors, warnings


def build_flat(expanded, resolver):
    """Build ``(components, nets)`` from an expanded spec.

    components: physical references plus their logical paths and source metadata.
    nets:       list of ``{name, kind, nodes: [(ref, pin_number)]}``.
    """
    components = []
    reference_map = expanded.get("reference_map", {}) or {}
    for name in sorted(expanded.get("instances", {})):
        inst = expanded["instances"][name]
        part_ref = inst.get("part", "")
        kind, part = resolver.resolve(part_ref)
        description = (
            part.get("description", "") if kind in ("library", "physical") and part else ""
        )
        value = inst["value"] if "value" in inst else split_part(part_ref)[1]
        fp = inst.get("footprint") or resolver.footprint(kind, part) or ""
        source = resolver.source(kind, part)
        components.append(
            {
                "ref": reference_map.get(name, name),
                "logical_path": name,
                "part": part_ref,
                "value": value,
                "footprint": fp,
                "description": description,
                "supplier_id": source.get("supplier_id", ""),
                "dnp": bool(inst.get("dnp")),
            }
        )

    nets = []
    for conn in expanded.get("connections", []) or []:
        nodes = []
        for ep in conn.get("endpoints", []) or []:
            parsed = parse_endpoint(ep)
            if not parsed:
                continue
            inst, token = parsed
            leaf = expanded["instances"].get(inst)
            if leaf is None:
                continue
            kind, part = resolver.resolve(leaf.get("part", ""))
            for p in resolve_pins(resolver.pins(kind, part), token):
                nodes.append((reference_map.get(inst, inst), str(p.get("number"))))
        nets.append(
            {"name": conn.get("net"), "kind": conn.get("kind"), "nodes": _dedupe(nodes)}
        )
    return components, nets
