"""Protel2 (Altium) text netlist exporter.

Emits the EasyEDA Pro-flavoured ``PROTEL NETLIST 2.0`` text form. Component
blocks use named fields, matching the format returned by
``eda.sch_Netlist.getNetlist('Protel2')``.

Format (keyed component blocks, then fully-qualified net nodes)::

    PROTEL NETLIST 2.0
    [
    DESIGNATOR
    U1
    FOOTPRINT
    Package_QFP:LQFP-48_7x7mm_P0.5mm
    PARTTYPE
    STM32F103C8T6
    Component Kind
    Standard
    Add into BOM
    yes
    Convert to PCB
    yes
    Designator
    U1
    Device
    STM32F103C8T6
    Unique ID
    U1
    Name
    STM32F103C8T6

    *
    ]
    (
    3V3
    U1-24 STM32F103C8T6-VDD_1 POWER
    C1-1 100nF-1 PASSIVE
    )
"""

from __future__ import annotations

import re

from ..core import build_flat

_REF_RE = re.compile(r"^([A-Za-z]+)(\d+)$")

_PIN_TYPE_TO_PROTEL2 = {
    "input": "INPUT",
    "output": "OUTPUT",
    "bidirectional": "BIDIRECTIONAL",
    "tri_state": "HI Z",
    "passive": "PASSIVE",
    "power_in": "POWER",
    "power_out": "POWER",
    "open_collector": "OPEN COLLECTOR",
    "open_emitter": "OPEN EMITTER",
    "no_connect": "NO CONNECT",
    "free": "UNDEFINED",
    "unspecified": "UNDEFINED",
}


def _ref_key(ref):
    m = _REF_RE.match(ref)
    if m:
        return (m.group(1), int(m.group(2)), ref)
    return (ref, 0, ref)


def _field(value) -> str:
    """Keep a Protel2 field on one physical line."""
    return str(value or "").replace("\r", " ").replace("\n", " ")


def _node_line(component, pin_number, resolver) -> str:
    """Render the extended Protel2 node form required by EasyEDA Pro.

    EasyEDA's PCB importer expects the legacy component-pin token followed by
    ``PARTTYPE-PINNAME`` and the electrical type. A bare ``R1-1`` token is
    accepted by some Protel readers but is silently ignored by EasyEDA Pro's
    current import preview.
    """
    kind, part = resolver.resolve(component["part"])
    pin = next(
        (
            item
            for item in resolver.pins(kind, part)
            if str(item.get("number")) == str(pin_number)
        ),
        {},
    )
    source = resolver.source(kind, part)
    part_type = _field(
        source.get("device_name")
        or source.get("manufacturer_part_number")
        or component["value"]
    ).replace(" ", "_") or "PART"
    pin_name = _field(pin.get("name") or pin_number).replace(" ", "_")
    electrical_type = _PIN_TYPE_TO_PROTEL2.get(
        str(pin.get("type") or "unspecified"), "UNDEFINED"
    )
    return f"{component['ref']}-{pin_number} {part_type}-{pin_name} {electrical_type}"


def render_protel2_netlist(expanded, resolver) -> str:
    components, nets = build_flat(expanded, resolver)
    components = sorted(components, key=lambda c: _ref_key(c["ref"]))
    components_by_ref = {component["ref"]: component for component in components}

    lines = ["PROTEL NETLIST 2.0"]
    for c in components:
        kind, part = resolver.resolve(c["part"])
        source = resolver.source(kind, part)
        part_name = c["part"].partition(":")[2] or c["part"]
        device_name = source.get("device_name") or part_name
        part_type = source.get("device_name") or source.get(
            "manufacturer_part_number"
        ) or c["value"]
        lines.append("[")
        lines.append("DESIGNATOR")
        lines.append(c["ref"])
        lines.append("FOOTPRINT")
        lines.append(_field(c["footprint"]))
        lines.append("PARTTYPE")
        lines.append(_field(part_type))
        lines.append("DESCRIPTION")
        lines.append(_field(c["description"]))
        lines.append("Component Kind")
        lines.append("Standard")
        lines.append("Add into BOM")
        lines.append("no" if c["dnp"] else "yes")
        lines.append("Convert to PCB")
        lines.append("yes")
        if source.get("symbol_name"):
            lines.append("Symbol")
            lines.append(_field(source["symbol_name"]))
        lines.append("Designator")
        lines.append(c["ref"])
        lines.append("Device")
        lines.append(_field(device_name))
        lines.append("Unique ID")
        lines.append(c["ref"])
        lines.append("Name")
        lines.append(_field(c["value"]))
        if source.get("manufacturer"):
            lines.append("Manufacturer")
            lines.append(_field(source["manufacturer"]))
        if source.get("manufacturer_part_number"):
            lines.append("Manufacturer Part")
            lines.append(_field(source["manufacturer_part_number"]))
        if c["supplier_id"]:
            lines.append("Supplier")
            lines.append(_field(source.get("supplier") or "LCSC"))
            lines.append("Supplier Part")
            lines.append(_field(c["supplier_id"]))
        lines.append("")
        lines.append("*")
        lines.append("]")
    for net in nets:
        lines.append("(")
        lines.append(net["name"])
        for ref, pin in net["nodes"]:
            lines.append(_node_line(components_by_ref[ref], pin, resolver))
        lines.append(")")
    return "\n".join(lines) + "\n"


def parse_protel2_netlist(text: str) -> dict:
    """Parse the component and net identity needed for deterministic comparison."""
    lines = [line.rstrip("\r") for line in text.splitlines()]
    components = {}
    nets = {}
    index = 1 if lines and lines[0].strip() == "PROTEL NETLIST 2.0" else 0

    while index < len(lines):
        token = lines[index].strip()
        if token not in {"[", "("}:
            index += 1
            continue
        closing = "]" if token == "[" else ")"
        end = index + 1
        while end < len(lines) and lines[end].strip() != closing:
            end += 1
        body = lines[index + 1 : end]
        if token == "[":
            if body and body[0].strip().upper() == "DESIGNATOR":
                fields = {}
                field_index = 0
                while field_index + 1 < len(body):
                    key = body[field_index].strip()
                    if key == "*":
                        break
                    fields[key.upper()] = body[field_index + 1]
                    field_index += 2
                ref = fields.get("DESIGNATOR", "")
                if ref:
                    components[ref] = {
                        "footprint": fields.get("FOOTPRINT", ""),
                        "parttype": fields.get("PARTTYPE", ""),
                    }
            elif body:
                ref = body[0].strip()
                if ref:
                    components[ref] = {
                        "footprint": body[1] if len(body) > 1 else "",
                        "parttype": body[2] if len(body) > 2 else "",
                    }
        elif body:
            name = body[0].strip()
            nodes = []
            for node in body[1:]:
                node_token = node.strip().split(maxsplit=1)[0] if node.strip() else ""
                if "-" not in node_token:
                    continue
                ref, pin = node_token.split("-", 1)
                nodes.append((ref.strip(), pin.strip()))
            if name:
                nets[name] = sorted(set(nodes))
        index = end + 1

    return {"components": components, "nets": nets}
