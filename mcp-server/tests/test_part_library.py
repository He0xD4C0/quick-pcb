"""Contracts for the read-only EasyEDA system-library candidate table."""

from __future__ import annotations

from boardspec_mcp import part_library


def _candidate(**overrides):
    item = {
        "uuid": "device-1",
        "libraryUuid": "system-library",
        "ordinal": 4,
        "name": "CL05B104KO5NNNC",
        "description": "100nF 16V X7R",
        "manufacturer": "Samsung",
        "manufacturerId": "CL05B104KO5NNNC",
        "supplier": "LCSC",
        "supplierId": "C1525",
        "symbolName": "CL05B104KO5NNNC",
        "symbolUuid": "symbol-1",
        "footprintName": "C0402",
        "footprintUuid": "footprint-1",
        "model3DName": "C0402",
        "model3DUuid": "model-1",
        "classification": {"primaryClassificationUuid": "capacitor"},
        "otherProperty": {
            "LCSC Part Name": "100nF ±10% 16V",
            "Supplier Part": "C1525",
            "Manufacturer": "Samsung",
            "Manufacturer Part": "CL05B104KO5NNNC",
            "Supplier Footprint": "0402",
            "JLCPCB Part Class": "Basic Part",
            "Datasheet": "https://example.test/C1525.pdf",
            "Add into BOM": "yes",
            "Convert to PCB": "yes",
            "Symbol": "symbol-1",
            "Footprint": "footprint-1",
            "3D Model": "model-1",
            "Value": "100nF",
            "Tolerance": "±10%",
            "Voltage Rating": "16V",
        },
    }
    item.update(overrides)
    return item


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.code = ""

    def execute(self, code):
        self.code = code
        return self.result


def _rows(result):
    fields = result["parts"]["fields"]
    return [dict(zip(fields, values)) for values in result["parts"]["rows"]]


def test_normalize_part_candidate_preserves_selection_attributes_and_provenance():
    row = part_library.normalize_part_candidate(_candidate(), 0)

    assert row["lcsc_id"] == "C1525"
    assert row["manufacturer_part_number"] == "CL05B104KO5NNNC"
    assert row["jlcpcb_part_class"] == "Basic Part"
    assert row["add_into_bom"] is True
    assert row["convert_to_pcb"] is True
    assert row["cad_complete"] is True
    assert row["attributes"] == {
        "Tolerance": "±10%",
        "Value": "100nF",
        "Voltage Rating": "16V",
    }
    assert row["issues"] == []


def test_sparse_candidate_is_not_filled_with_guesses():
    row = part_library.normalize_part_candidate(
        {"uuid": "device-2", "libraryUuid": "system-library", "name": "USB-C"},
        0,
    )

    assert row["manufacturer"] is None
    assert row["datasheet_url"] is None
    assert row["cad_complete"] is False
    assert row["attributes"] == {}
    assert row["issues"] == [
        "MISSING_LCSC_ID",
        "MISSING_MANUFACTURER",
        "MISSING_SYMBOL",
        "MISSING_FOOTPRINT",
        "MISSING_3D_MODEL",
        "MISSING_DATASHEET",
    ]


def test_search_parts_returns_fixed_columnar_contract_and_pagination():
    client = FakeClient({"ok": True, "result": [_candidate()]})

    result = part_library.search_parts(client, " 100nF 0402 ", page=2, page_size=1)

    assert result["ok"] is True
    assert result["format"] == "parts/easyeda-v0.1"
    assert result["source"] == {
        "provider": "easyeda-pro",
        "scope": "system-library",
    }
    assert result["query"] == {"kind": "keyword", "query": "100nF 0402"}
    assert result["page"] == 2
    assert result["page_size"] == 1
    assert result["next_page"] == 3
    assert result["parts"]["fields"] == part_library.PART_FIELDS
    assert _rows(result)[0]["lcsc_id"] == "C1525"
    assert 'eda.lib_Device.search("100nF 0402"' in client.code
    assert client.code.endswith(", 1, 2);")


def test_empty_search_returns_warning_not_fabricated_rows():
    result = part_library.search_parts(
        FakeClient({"ok": True, "result": []}), "not-a-real-part", page_size=10
    )

    assert result["ok"] is True
    assert result["returned"] == 0
    assert result["next_page"] is None
    assert result["warnings"][0]["code"] == "PARTS_NOT_FOUND"


def test_search_validation_happens_before_bridge():
    class UnexpectedClient:
        def execute(self, code):
            raise AssertionError("invalid queries must not reach EasyEDA")

    assert part_library.search_parts(UnexpectedClient(), " ")["code"] == "INVALID_PART_QUERY"
    assert part_library.search_parts(UnexpectedClient(), "R", page=0)["code"] == "INVALID_PART_QUERY"
    assert part_library.search_parts(UnexpectedClient(), "R", page_size=51)["code"] == "INVALID_PART_QUERY"


def test_lcsc_lookup_normalizes_deduplicates_and_preserves_all_matches():
    first = _candidate(uuid="device-1", supplierId="C1525")
    second = _candidate(uuid="device-2", supplierId="C1525", ordinal=5)
    client = FakeClient({"ok": True, "result": [second, first]})

    result = part_library.get_parts_by_lcsc_ids(client, [" c1525 ", "C1525"])

    assert result["query"] == {"kind": "lcsc_ids", "lcsc_ids": ["C1525"]}
    assert result["returned"] == 2
    assert [row["device_uuid"] for row in _rows(result)] == ["device-1", "device-2"]
    assert result["missing_lcsc_ids"] == []
    assert "getByLcscIds([\"C1525\"], undefined, true)" in client.code


def test_lcsc_lookup_reports_missing_ids_without_failing_matches():
    client = FakeClient({"ok": True, "result": [_candidate()]})

    result = part_library.get_parts_by_lcsc_ids(client, ["C1525", "C99999999"])

    assert result["ok"] is True
    assert result["returned"] == 1
    assert result["missing_lcsc_ids"] == ["C99999999"]
    assert result["warnings"][0]["code"] == "PARTS_NOT_FOUND"


def test_lcsc_lookup_rejects_invalid_or_excessive_unique_ids():
    invalid, error = part_library.normalize_lcsc_ids(["1525"])
    assert invalid is None
    assert error["code"] == "INVALID_PART_QUERY"

    excessive = [f"C{index}" for index in range(1, 52)]
    normalized, error = part_library.normalize_lcsc_ids(excessive)
    assert normalized is None
    assert error["code"] == "INVALID_PART_QUERY"


def test_library_queries_propagate_transport_failure_and_reject_bad_shapes():
    offline = FakeClient(
        {"ok": False, "code": "BRIDGE_UNAVAILABLE", "message": "offline"}
    )
    assert part_library.search_parts(offline, "STM32")["code"] == "BRIDGE_UNAVAILABLE"

    malformed = FakeClient({"ok": True, "result": {"uuid": "not-a-table"}})
    assert part_library.search_parts(malformed, "STM32")["code"] == "LIBRARY_BAD_RESPONSE"
    assert part_library.get_parts_by_lcsc_ids(malformed, ["C1525"])["code"] == "LIBRARY_BAD_RESPONSE"
