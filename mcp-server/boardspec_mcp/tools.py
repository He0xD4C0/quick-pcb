"""Tool implementations for the BoardSpec MCP server."""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
import tempfile
import zipfile

from .bridge_client import BridgeClient
from .core_tools import expand, export, validate

_EASYEDA_PIN_TYPES = {
    "in": "input",
    "input": "input",
    "out": "output",
    "output": "output",
    "bi": "bidirectional",
    "bidirectional": "bidirectional",
    "passive": "passive",
    "open collector": "open_collector",
    "open-collector": "open_collector",
    "open drain": "open_collector",
    "open-drain": "open_collector",
    "open emitter": "open_emitter",
    "open-emitter": "open_emitter",
    "hiz": "tri_state",
    "high impedance": "tri_state",
    "tri-state": "tri_state",
    "tri_state": "tri_state",
}


def normalize_electrical_type(raw_type) -> str:
    """Map EasyEDA pin types without treating Power/Ground as directional."""
    normalized = str(raw_type or "").strip().lower()
    return _EASYEDA_PIN_TYPES.get(normalized, "unspecified")


def _physical_definition(device: dict, footprint_name: str | None = None) -> dict:
    association = device.get("association") or {}
    symbol = association.get("symbol") or {}
    footprint = association.get("footprint") or {}
    properties = device.get("property") or {}
    other = properties.get("otherProperty") or {}
    designator = str(properties.get("designator") or other.get("Designator") or "")
    prefix_match = re.match(r"[A-Za-z]+", designator)
    raw_pin_types = {
        str(pin.get("number")): str(pin.get("type") or "")
        for pin in device.get("pins", [])
    }
    source = {
        "provider": "easyeda-pro",
        "library_uuid": device.get("libraryUuid") or symbol.get("libraryUuid"),
        "device_uuid": device.get("uuid"),
        "device_name": device.get("name"),
        "symbol_uuid": symbol.get("uuid") or association.get("symbolUuid"),
        "symbol_name": (
            str((device.get("subPartNames") or [""])[0]).rsplit(".", 1)[0]
            or device.get("name")
        ),
        "footprint_uuid": footprint.get("uuid") or association.get("footprintUuid"),
        "supplier": properties.get("supplier"),
        "supplier_id": properties.get("supplierId"),
        "manufacturer": properties.get("manufacturer"),
        "manufacturer_part_number": properties.get("manufacturerId"),
        "raw_pin_types": raw_pin_types,
    }
    source = {key: value for key, value in source.items() if value not in (None, "")}
    definition = {
        "kind": "physical",
        "description": device.get("description") or "",
        "pins": [
            {
                "number": str(pin.get("number")),
                "name": str(pin.get("name") or pin.get("number")),
                "type": normalize_electrical_type(pin.get("type")),
            }
            for pin in device.get("pins", [])
        ],
        "symbol": source.get("symbol_uuid", ""),
        "source": source,
        "review": {"status": "unreviewed", "pin_type_authority": "source_library"},
    }
    if prefix_match:
        definition["reference_prefix"] = prefix_match.group(0)
    if footprint_name:
        definition["footprint"] = footprint_name
    return definition


def bridge_status(client: BridgeClient) -> dict:
    return client.health()


def search_part(client: BridgeClient, query: str, limit: int = 10) -> dict:
    code = (
        "return await eda.lib_Device.search("
        + json.dumps(query)
        + ", undefined, undefined, undefined, "
        + str(int(limit))
        + ", 1);"
    )
    return client.execute(code)


def _pin_warning(message: str) -> dict:
    return {
        "code": "PIN_DATA_UNAVAILABLE",
        "path": "/result/pins",
        "message": message,
        "hint": "Confirm the symbol in EasyEDA before using its pins in a BoardSpec.",
    }


def _extract_symbol_pins(encoded_archive: str) -> list[dict]:
    raw = base64.b64decode(encoded_archive, validate=True)
    pins: dict[str, dict] = {}
    attributes: list[dict] = []

    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        source_names = [name for name in archive.namelist() if name.endswith(".elibu")]
        if not source_names:
            raise ValueError("symbol archive contains no .elibu source")
        source = archive.read(source_names[0]).decode("utf-8")

    for line in source.splitlines():
        if "||" not in line:
            continue
        header_text, body_text = line.split("||", 1)
        try:
            header = json.loads(header_text)
            body = json.loads(body_text.removesuffix("|"))
        except (json.JSONDecodeError, TypeError):
            continue
        record_type = header.get("type")
        if record_type == "PIN":
            pin_id = str(header.get("id", ""))
            if pin_id:
                pins[pin_id] = {
                    "number": None,
                    "name": None,
                    "type": body.get("electric"),
                    "part": body.get("partId"),
                }
        elif record_type == "ATTR":
            attributes.append(body)

    fields = {
        "pinname": "name",
        "name": "name",
        "pinnumber": "number",
        "number": "number",
        "pintype": "type",
        "electricaltype": "type",
    }
    for attribute in attributes:
        pin = pins.get(str(attribute.get("parentId", "")))
        key = str(attribute.get("key", "")).lower().replace(" ", "").replace("_", "")
        field = fields.get(key)
        if pin is not None and field is not None:
            pin[field] = attribute.get("value")

    resolved = [pin for pin in pins.values() if pin["number"] is not None or pin["name"]]
    if not resolved:
        raise ValueError("symbol source contains no resolvable pins")

    def sort_key(pin: dict):
        number = str(pin.get("number") or "")
        return (0, int(number)) if number.isdigit() else (1, number)

    return sorted(resolved, key=sort_key)


def get_part(client: BridgeClient, part_uuid: str, library_uuid: str = "") -> dict:
    lib_arg = json.dumps(library_uuid) if library_uuid else "undefined"
    code = (
        "return await eda.lib_Device.get("
        + json.dumps(part_uuid)
        + ", "
        + lib_arg
        + ");"
    )
    response = client.execute(code)
    if not response.get("ok") or not isinstance(response.get("result"), dict):
        return response

    device = response["result"]
    symbol = device.get("association", {}).get("symbol", {})
    symbol_uuid = symbol.get("uuid")
    symbol_library_uuid = symbol.get("libraryUuid") or library_uuid
    if not symbol_uuid:
        response["warnings"] = [_pin_warning("device has no associated schematic symbol")]
        return response

    archive_code = (
        "const f=await eda.sys_FileManager.getSymbolFileBySymbolUuid("
        + json.dumps(symbol_uuid)
        + ", "
        + json.dumps(symbol_library_uuid)
        + ", 'elibz2');"
        "if(!f)return null;"
        "const bytes=new Uint8Array(await f.arrayBuffer());"
        "let binary='';"
        "for(let i=0;i<bytes.length;i+=8192){"
        "binary+=String.fromCharCode(...bytes.subarray(i,i+8192));"
        "}"
        "return btoa(binary);"
    )
    archive_response = client.execute(archive_code)
    encoded_archive = archive_response.get("result") if archive_response.get("ok") else None
    if not isinstance(encoded_archive, str):
        message = archive_response.get("message", "symbol archive was not returned")
        response["warnings"] = [_pin_warning(message)]
        return response

    try:
        device["pins"] = _extract_symbol_pins(encoded_archive)
    except (binascii.Error, UnicodeDecodeError, ValueError, zipfile.BadZipFile) as exc:
        response["warnings"] = [_pin_warning(f"could not parse symbol pins: {exc}")]
        return response
    device["pinSource"] = {
        "kind": "EasyEDA symbol archive",
        "symbolUuid": symbol_uuid,
        "libraryUuid": symbol_library_uuid,
    }
    footprint = device.get("association", {}).get("footprint") or {}
    footprint_uuid = footprint.get("uuid") or device.get("association", {}).get(
        "footprintUuid"
    )
    footprint_library_uuid = footprint.get("libraryUuid") or library_uuid
    footprint_name = None
    if footprint_uuid:
        footprint_code = (
            "return await eda.lib_Footprint.get("
            + json.dumps(footprint_uuid)
            + ", "
            + json.dumps(footprint_library_uuid)
            + ");"
        )
        footprint_response = client.execute(footprint_code)
        footprint_result = footprint_response.get("result")
        if footprint_response.get("ok") and isinstance(footprint_result, dict):
            footprint_name = footprint_result.get("name")

    response["board_spec_definition"] = _physical_definition(device, footprint_name)
    unresolved_types = [
        pin for pin in device["pins"]
        if str(pin.get("type") or "").lower() in {"", "undefined", "unknown"}
    ]
    if unresolved_types:
        response["warnings"] = [
            {
                "code": "PIN_TYPES_UNRESOLVED",
                "path": "/result/pins",
                "message": (
                    f"{len(unresolved_types)} of {len(device['pins'])} pins have no usable "
                    "electrical type in the EasyEDA symbol"
                ),
                "hint": "Verify electrical pin types from an approved source before ERC.",
            }
        ]
    return response


def get_project_component(client: BridgeClient, designator: str) -> dict:
    """Read one placed schematic component and its live pin state."""
    code = """
const wanted = %s;
const components = await eda.sch_PrimitiveComponent.getAll(undefined, true);
const matches = components.filter(c => c.getState_Designator() === wanted);
const result = [];
for (const component of matches) {
  const pins = await component.getAllPins() || [];
  result.push({
    primitiveId: component.getState_PrimitiveId(),
    designator: component.getState_Designator(),
    name: component.getState_Name(),
    component: component.getState_Component(),
    symbol: component.getState_Symbol(),
    footprint: component.getState_Footprint(),
    pins: pins.map(pin => ({
      number: pin.getState_PinNumber(),
      name: pin.getState_PinName(),
      type: pin.getState_pinType(),
      noConnected: Boolean(pin.getState_NoConnected())
    }))
  });
}
return result;
""" % json.dumps(designator)
    response = client.execute(code)
    if not response.get("ok"):
        return response
    matches = response.get("result")
    if not isinstance(matches, list) or not matches:
        return {
            "ok": False,
            "code": "COMPONENT_NOT_FOUND",
            "message": f"no placed schematic component has designator '{designator}'",
        }
    if len(matches) != 1:
        return {
            "ok": False,
            "code": "AMBIGUOUS_COMPONENT",
            "message": f"{len(matches)} components have designator '{designator}'",
        }
    return {"ok": True, "result": matches[0]}


def get_netlist(
    client: BridgeClient,
    netlist_type: str = "PROTEL2",
    document_kind: str = "schematic",
) -> dict:
    """Read the current schematic or PCB netlist without modifying the project."""
    type_map = {
        "PROTEL2": "Protel2",
        "JLCEDA": "JLCEDA",
        "ALLEGRO": "Allegro",
        "PADS": "PADS",
    }
    target = type_map.get(netlist_type.upper())
    if target is None:
        return {
            "ok": False,
            "code": "UNKNOWN_NETLIST_TYPE",
            "message": f"unknown netlist type '{netlist_type}'",
        }
    api_by_kind = {"schematic": "sch_Netlist", "pcb": "pcb_Net"}
    api = api_by_kind.get(document_kind.lower())
    if api is None:
        return {
            "ok": False,
            "code": "UNKNOWN_DOCUMENT_KIND",
            "message": f"unknown document kind '{document_kind}'",
        }
    response = client.execute(
        f"return await eda.{api}.getNetlist(" + json.dumps(target) + ");"
    )
    if response.get("ok"):
        response["netlist_type"] = netlist_type.upper()
        response["document_kind"] = document_kind.lower()
    return response


def set_no_connects(
    client: BridgeClient, designator: str, pin_selectors: list[str], apply: bool = False
) -> dict:
    """Preview or set explicit no-connect flags on selected placed-component pins."""
    if len(pin_selectors) != len(set(pin_selectors)):
        return {
            "ok": False,
            "code": "DUPLICATE_NO_CONNECT",
            "message": "pin_selectors contains duplicates",
        }
    invalid = [pin for pin in pin_selectors if not re.fullmatch(r"#[A-Za-z0-9_.+/-]+", pin)]
    if invalid:
        return {
            "ok": False,
            "code": "INVALID_PIN_SELECTOR",
            "message": "no-connect selectors must use exact #PIN_NUMBER syntax",
        }
    code = """
const wanted = %s;
const requested = %s;
const shouldApply = %s;
const components = await eda.sch_PrimitiveComponent.getAll(undefined, true);
const matches = components.filter(c => c.getState_Designator() === wanted);
if (matches.length !== 1) return {matchCount: matches.length};
const component = matches[0];
let pins = await component.getAllPins() || [];
const selected = pins.filter(pin => requested.includes('#' + pin.getState_PinNumber()));
const before = selected.map(pin => ({
  number: pin.getState_PinNumber(),
  noConnected: Boolean(pin.getState_NoConnected())
}));
if (shouldApply) {
  for (const pin of selected) {
    if (!pin.getState_NoConnected()) {
      const pending = pin.toAsync();
      pending.setState_NoConnected(true);
      await pending.done();
    }
  }
  const refreshed = await eda.sch_PrimitiveComponent.get(component.getState_PrimitiveId());
  pins = await refreshed.getAllPins() || [];
}
const after = pins
  .filter(pin => requested.includes('#' + pin.getState_PinNumber()))
  .map(pin => ({number: pin.getState_PinNumber(), noConnected: Boolean(pin.getState_NoConnected())}));
const found = after.map(pin => '#' + pin.number);
return {matchCount: 1, requested, found, before, after};
""" % (json.dumps(designator), json.dumps(pin_selectors), "true" if apply else "false")
    response = client.execute(code)
    if not response.get("ok"):
        return response
    result = response.get("result") or {}
    if result.get("matchCount") != 1:
        return {
            "ok": False,
            "code": "COMPONENT_NOT_FOUND" if result.get("matchCount") == 0 else "AMBIGUOUS_COMPONENT",
            "message": f"expected one '{designator}' component, found {result.get('matchCount', 0)}",
        }
    missing = sorted(set(pin_selectors) - set(result.get("found") or []))
    if missing:
        return {
            "ok": False,
            "code": "UNKNOWN_PIN",
            "message": f"pins not found on '{designator}': {', '.join(missing)}",
        }
    response.update({"applied": apply, "preview": not apply})
    return response


def run_schematic_drc(client: BridgeClient) -> dict:
    """Run strict schematic DRC and return detailed violations without opening UI."""
    response = client.execute("return await eda.sch_Drc.check(true, false, true);")
    if response.get("ok"):
        violations = response.get("result")
        response["passed"] = isinstance(violations, list) and not violations
    return response


def run_pcb_drc(client: BridgeClient) -> dict:
    """Run strict PCB DRC and return detailed violations without opening UI."""
    response = client.execute("return await eda.pcb_Drc.check(true, false, true);")
    if response.get("ok"):
        violations = response.get("result")
        response["passed"] = isinstance(violations, list) and not violations
    return response


def load_netlist(
    client: BridgeClient,
    netlist_text: str,
    netlist_type: str = "PROTEL2",
    document_kind: str = "pcb",
) -> dict:
    """Stage a netlist import against the active EasyEDA PCB by default.

    EasyEDA Pro's import confirmation is a PCB operation. The schematic API is
    retained as an explicit compatibility option, but it does not synthesize
    wires or labels from an arbitrary netlist.
    """
    type_map = {
        "PROTEL2": "Protel2",
        "JLCEDA": "JLCEDA",
        "ALLEGRO": "Allegro",
        "PADS": "PADS",
    }
    t = type_map.get(netlist_type.upper())
    if t is None:
        return {
            "ok": False,
            "code": "UNKNOWN_NETLIST_TYPE",
            "message": f"unknown netlist type '{netlist_type}'",
        }
    api_by_kind = {"pcb": "pcb_Net", "schematic": "sch_Netlist"}
    api = api_by_kind.get(document_kind.lower())
    if api is None:
        return {
            "ok": False,
            "code": "UNKNOWN_DOCUMENT_KIND",
            "message": f"unknown document kind '{document_kind}'",
        }
    if not netlist_text.strip():
        return {
            "ok": False,
            "code": "INVALID_NETLIST",
            "message": "netlist_text is empty",
        }
    if netlist_type.upper() == "PROTEL2":
        normalized = netlist_text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.startswith("PROTEL NETLIST 2.0") or not re.search(
            r"(?m)^\[$", normalized
        ):
            return {
                "ok": False,
                "code": "INVALID_NETLIST",
                "message": "PROTEL2 netlist has no component records",
            }
    if netlist_type.upper() == "PROTEL2":
        netlist_text = netlist_text.replace("\r\n", "\n").replace("\r", "\n")
        if not netlist_text.endswith("\n"):
            netlist_text += "\n"
        netlist_text = netlist_text.replace("\n", "\r\n")
    code = (
        f"return await eda.{api}.setNetlist("
        + json.dumps(t)
        + ", "
        + json.dumps(netlist_text)
        + ");"
    )
    response = client.execute(code)
    if response.get("ok"):
        response.update(
            {
                "staged": True,
                "requires_user_confirmation": True,
                "document_kind": document_kind.lower(),
                "message": (
                    "Netlist import is open in EasyEDA for review; choose Apply Changes "
                    "in the EDA window to commit it."
                ),
            }
        )
    return response


def _file_to_spec(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()
