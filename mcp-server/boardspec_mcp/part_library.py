"""Deterministic, token-conscious EasyEDA system-library queries."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from .bridge_client import BridgeClient

PARTS_FORMAT = "parts/easyeda-v0.1"
MAX_PAGE_SIZE = 50
MAX_LCSC_IDS = 50
MAX_QUERY_LENGTH = 200
_LCSC_ID = re.compile(r"^C[1-9][0-9]*$")

PART_FIELDS = [
    "ordinal",
    "device_uuid",
    "library_uuid",
    "lcsc_id",
    "name",
    "manufacturer",
    "manufacturer_part_number",
    "description",
    "lcsc_part_name",
    "classification",
    "supplier_footprint",
    "jlcpcb_part_class",
    "add_into_bom",
    "convert_to_pcb",
    "datasheet_url",
    "symbol_name",
    "symbol_uuid",
    "footprint_name",
    "footprint_uuid",
    "model_3d_name",
    "model_3d_uuid",
    "has_symbol",
    "has_footprint",
    "has_3d_model",
    "cad_complete",
    "attributes",
    "issues",
]

_COMMON_ATTRIBUTE_KEYS = {
    "3D Model",
    "3D Model Title",
    "3D Model Transform",
    "Add into BOM",
    "Convert to PCB",
    "Datasheet",
    "Designator",
    "Footprint",
    "JLCPCB Part Class",
    "LCSC Part Name",
    "Manufacturer",
    "Manufacturer Part",
    "Name",
    "Supplier",
    "Supplier Footprint",
    "Supplier Part",
    "Symbol",
}


def _columnar(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {
        "fields": PART_FIELDS,
        "rows": [[row.get(field) for field in PART_FIELDS] for row in rows],
    }


def _value(item: dict[str, Any], properties: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
        value = properties.get(key)
        if value not in (None, ""):
            return value
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def normalize_part_candidate(item: dict[str, Any], ordinal: int) -> dict[str, Any]:
    """Normalize one heterogeneous EasyEDA search item without guessing values."""
    properties = item.get("otherProperty")
    if not isinstance(properties, dict):
        properties = {}

    symbol = item.get("symbol") if isinstance(item.get("symbol"), dict) else {}
    footprint = (
        item.get("footprint") if isinstance(item.get("footprint"), dict) else {}
    )
    model_3d = item.get("model3D") if isinstance(item.get("model3D"), dict) else {}

    symbol_name = _optional_text(symbol.get("name") or item.get("symbolName"))
    symbol_uuid = _optional_text(symbol.get("uuid") or item.get("symbolUuid"))
    footprint_name = _optional_text(
        footprint.get("name") or item.get("footprintName")
    )
    footprint_uuid = _optional_text(
        footprint.get("uuid") or item.get("footprintUuid")
    )
    model_3d_name = _optional_text(
        model_3d.get("name") or item.get("model3DName")
    )
    model_3d_uuid = _optional_text(
        model_3d.get("uuid") or item.get("model3DUuid")
    )

    lcsc_id = _optional_text(_value(item, properties, "supplierId", "Supplier Part"))
    manufacturer = _optional_text(_value(item, properties, "manufacturer", "Manufacturer"))
    manufacturer_part_number = _optional_text(
        _value(item, properties, "manufacturerId", "Manufacturer Part")
    )
    datasheet_url = _optional_text(properties.get("Datasheet"))

    issues: list[str] = []
    if not item.get("uuid"):
        issues.append("MISSING_DEVICE_UUID")
    if not lcsc_id:
        issues.append("MISSING_LCSC_ID")
    if not manufacturer:
        issues.append("MISSING_MANUFACTURER")
    if not symbol_uuid:
        issues.append("MISSING_SYMBOL")
    if not footprint_uuid:
        issues.append("MISSING_FOOTPRINT")
    if not model_3d_uuid:
        issues.append("MISSING_3D_MODEL")
    if not datasheet_url:
        issues.append("MISSING_DATASHEET")

    attributes = {
        str(key): value
        for key, value in sorted(properties.items(), key=lambda pair: str(pair[0]))
        if key not in _COMMON_ATTRIBUTE_KEYS and value not in (None, "")
    }

    has_symbol = bool(symbol_uuid)
    has_footprint = bool(footprint_uuid)
    has_3d_model = bool(model_3d_uuid)
    source_ordinal = item.get("ordinal")
    if not isinstance(source_ordinal, int):
        source_ordinal = ordinal

    return {
        "ordinal": source_ordinal,
        "device_uuid": _optional_text(item.get("uuid")),
        "library_uuid": _optional_text(item.get("libraryUuid")),
        "lcsc_id": lcsc_id,
        "name": _optional_text(item.get("name")),
        "manufacturer": manufacturer,
        "manufacturer_part_number": manufacturer_part_number,
        "description": _optional_text(item.get("description")),
        "lcsc_part_name": _optional_text(properties.get("LCSC Part Name")),
        "classification": item.get("classification"),
        "supplier_footprint": _optional_text(properties.get("Supplier Footprint")),
        "jlcpcb_part_class": _optional_text(properties.get("JLCPCB Part Class")),
        "add_into_bom": _optional_bool(properties.get("Add into BOM")),
        "convert_to_pcb": _optional_bool(properties.get("Convert to PCB")),
        "datasheet_url": datasheet_url,
        "symbol_name": symbol_name,
        "symbol_uuid": symbol_uuid,
        "footprint_name": footprint_name,
        "footprint_uuid": footprint_uuid,
        "model_3d_name": model_3d_name,
        "model_3d_uuid": model_3d_uuid,
        "has_symbol": has_symbol,
        "has_footprint": has_footprint,
        "has_3d_model": has_3d_model,
        "cad_complete": has_symbol and has_footprint,
        "attributes": attributes,
        "issues": issues,
    }


def _warning(code: str, path: str, message: str, hint: str | None = None) -> dict:
    return {
        "code": code,
        "path": path,
        "message": message,
        **({"hint": hint} if hint else {}),
    }


def _base_result(query: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": True,
        "format": PARTS_FORMAT,
        "source": {"provider": "easyeda-pro", "scope": "system-library"},
        "query": query,
        "returned": len(rows),
        "parts": _columnar(rows),
        "missing_lcsc_ids": [],
        "warnings": [],
    }


def search_parts(
    client: BridgeClient, query: str, page: int = 1, page_size: int = 10
) -> dict[str, Any]:
    normalized_query = str(query).strip()
    if not normalized_query:
        return {
            "ok": False,
            "code": "INVALID_PART_QUERY",
            "message": "query must contain at least one non-whitespace character",
        }
    if len(normalized_query) > MAX_QUERY_LENGTH:
        return {
            "ok": False,
            "code": "INVALID_PART_QUERY",
            "message": f"query must be at most {MAX_QUERY_LENGTH} characters",
        }
    if page < 1:
        return {
            "ok": False,
            "code": "INVALID_PART_QUERY",
            "message": "page must be at least 1",
        }
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        return {
            "ok": False,
            "code": "INVALID_PART_QUERY",
            "message": f"page_size must be between 1 and {MAX_PAGE_SIZE}",
        }

    code = (
        "return await eda.lib_Device.search("
        + json.dumps(normalized_query)
        + ", undefined, undefined, undefined, "
        + str(int(page_size))
        + ", "
        + str(int(page))
        + ");"
    )
    response = client.execute(code)
    if not response.get("ok"):
        return response
    raw_rows = response.get("result")
    if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
        return {
            "ok": False,
            "code": "LIBRARY_BAD_RESPONSE",
            "message": "EasyEDA device search returned a non-tabular result",
        }

    rows = [normalize_part_candidate(item, index) for index, item in enumerate(raw_rows)]
    result = _base_result(
        {"kind": "keyword", "query": normalized_query}, rows
    )
    result.update(
        {
            "page": page,
            "page_size": page_size,
            "next_page": page + 1 if len(rows) == page_size else None,
        }
    )
    if not rows:
        result["warnings"] = [
            _warning(
                "PARTS_NOT_FOUND",
                "/query/query",
                f"no EasyEDA system-library parts matched {normalized_query!r}",
                "Try a manufacturer part number, LCSC C number, package, or electrical value.",
            )
        ]
    return result


def normalize_lcsc_ids(lcsc_ids: list[str]) -> tuple[list[str] | None, dict | None]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in lcsc_ids:
        value = str(raw).strip().upper()
        if not _LCSC_ID.fullmatch(value):
            return None, {
                "ok": False,
                "code": "INVALID_PART_QUERY",
                "message": f"invalid LCSC part number: {raw!r}; expected C followed by digits",
            }
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    if not normalized:
        return None, {
            "ok": False,
            "code": "INVALID_PART_QUERY",
            "message": "lcsc_ids must contain at least one C number",
        }
    if len(normalized) > MAX_LCSC_IDS:
        return None, {
            "ok": False,
            "code": "INVALID_PART_QUERY",
            "message": f"lcsc_ids may contain at most {MAX_LCSC_IDS} unique C numbers",
        }
    return normalized, None


def get_parts_by_lcsc_ids(
    client: BridgeClient, lcsc_ids: list[str]
) -> dict[str, Any]:
    normalized, error = normalize_lcsc_ids(lcsc_ids)
    if error:
        return error
    assert normalized is not None

    code = (
        "return await eda.lib_Device.getByLcscIds("
        + json.dumps(normalized)
        + ", undefined, true);"
    )
    response = client.execute(code)
    if not response.get("ok"):
        return response
    raw_rows = response.get("result")
    if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
        return {
            "ok": False,
            "code": "LIBRARY_BAD_RESPONSE",
            "message": "EasyEDA C-number lookup returned a non-tabular result",
        }

    requested_order = {value: index for index, value in enumerate(normalized)}
    rows = [normalize_part_candidate(item, index) for index, item in enumerate(raw_rows)]
    rows.sort(
        key=lambda row: (
            requested_order.get(str(row.get("lcsc_id")), len(requested_order)),
            int(row.get("ordinal") or 0),
            str(row.get("device_uuid") or ""),
        )
    )
    found = {str(row.get("lcsc_id")) for row in rows if row.get("lcsc_id")}
    missing = [value for value in normalized if value not in found]

    result = _base_result({"kind": "lcsc_ids", "lcsc_ids": normalized}, rows)
    result.update(
        {
            "page": 1,
            "page_size": len(normalized),
            "next_page": None,
            "missing_lcsc_ids": missing,
        }
    )
    if missing:
        result["warnings"] = [
            _warning(
                "PARTS_NOT_FOUND",
                "/query/lcsc_ids",
                "no EasyEDA system-library match for: " + ", ".join(missing),
                "Verify the C numbers in the LCSC catalog before using them in a BOM.",
            )
        ]
    return result
