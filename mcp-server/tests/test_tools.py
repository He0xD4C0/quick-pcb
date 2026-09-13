"""Tests for MCP tool functions (local tools + bridge-degraded behavior)."""

from __future__ import annotations

import base64
import io
import os
import zipfile

import pytest

from boardspec_mcp import tools
from boardspec_mcp.bridge_client import BridgeClient
import httpx

FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..",
    "boardspec-core",
    "tests",
    "fixtures",
)
STATUS_LED = os.path.abspath(os.path.join(FIXTURES, "status-led.yaml"))
PARTS_DB = os.path.abspath(os.path.join(FIXTURES, "parts.demo.json"))


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [
        ("IN", "input"),
        ("OUT", "output"),
        ("BI", "bidirectional"),
        ("Passive", "passive"),
        ("Open Collector", "open_collector"),
        ("Open Emitter", "open_emitter"),
        ("Tri-State", "tri_state"),
        ("Undefined", "unspecified"),
        ("Power", "unspecified"),
        ("Ground", "unspecified"),
    ],
)
def test_easyeda_pin_type_mapping_is_explicit_and_power_is_conservative(
    raw_type, expected
):
    assert tools.normalize_electrical_type(raw_type) == expected


def _spec_text():
    # Rewrite the library path to the absolute demo DB so resolution works
    # regardless of the current working directory.
    with open(STATUS_LED, encoding="utf-8") as f:
        text = f.read()
    return text.replace(
        "path: parts.demo.json", f"path: {PARTS_DB}"
    )


def test_validate_ok():
    res = tools.validate(_spec_text())
    assert res["ok"] is True
    assert res["errors"] == []
    assert any(w["code"] == "INCOMPLETE_PART_DATA" for w in res["warnings"])


def test_validate_reports_errors():
    bad = _spec_text().replace("U1.PA5", "U1.NOPE")
    res = tools.validate(bad)
    assert res["ok"] is False
    assert any(e["code"] == "UNKNOWN_PIN" for e in res["errors"])


def test_validate_reports_malformed_yaml_as_diagnostic():
    res = tools.validate("spec: [")
    assert res["ok"] is False
    assert res["errors"][0]["code"] == "SCHEMA_INVALID"
    assert res["errors"][0]["path"] == "/"
    assert "line 1" in res["errors"][0]["message"]


def test_validate_uses_yaml_12_scalar_rules():
    text = _spec_text().replace("net: LED_CTRL", "net: ON")

    res = tools.expand(text)

    assert res["ok"] is True
    assert any(conn["net"] == "ON" for conn in res["expanded_spec"]["connections"])


def test_validate_rejects_duplicate_yaml_keys():
    res = tools.validate(
        """\
spec: board-spec/v0.1
project: {name: first, name: second}
instances: {}
connections: []
"""
    )

    assert res["ok"] is False
    assert res["errors"][0]["code"] == "SCHEMA_INVALID"
    assert "duplicate key" in res["errors"][0]["message"]


def test_expand_flattens_module():
    res = tools.expand(_spec_text())
    assert res["ok"] is True
    insts = res["expanded_spec"]["instances"]
    assert "LED1/R" in insts and "LED1/D" in insts


def test_export_protel2():
    res = tools.export(_spec_text(), "protel2_netlist")
    assert res["ok"] is True
    assert "3V3" in res["content"]
    assert "U1-24" in res["content"]


def test_export_unknown_target():
    res = tools.export(_spec_text(), "nope")
    assert res["ok"] is False
    assert res["errors"][0]["code"] == "UNKNOWN_TARGET"


def test_bridge_status_degrades_gracefully(monkeypatch):
    # No bridge running -> explicit BRIDGE_UNAVAILABLE, never fabricated data.
    client = BridgeClient(port_range=range(49630, 49631), timeout=0.5)
    res = client.health()
    assert res["ok"] is False
    assert res["code"] == "BRIDGE_UNAVAILABLE"


def test_search_part_degrades_gracefully():
    client = BridgeClient(port_range=range(49630, 49631), timeout=0.5)
    res = tools.search_part(client, "STM32", limit=5)
    assert res["ok"] is False
    assert res["code"] == "BRIDGE_UNAVAILABLE"


def test_bridge_execute_rejects_http_error(monkeypatch):
    client = BridgeClient(base_url="http://bridge.test")
    monkeypatch.setattr(client, "resolve_base_url", lambda: "http://bridge.test")
    response = httpx.Response(500, json={"result": "must not be accepted"})
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)

    res = client.execute("return 1")

    assert res == {
        "ok": False,
        "code": "BRIDGE_HTTP_ERROR",
        "message": "bridge returned HTTP 500",
    }


def test_bridge_health_requires_connected_eda(monkeypatch):
    client = BridgeClient(base_url="http://bridge.test")
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "http://bridge.test/health"),
        json={
            "service": "easyeda-bridge",
            "edaConnected": False,
            "edaWindowCount": 0,
            "activeWindowId": None,
        },
    )
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: response)

    res = client.health()

    assert res["ok"] is False
    assert res["code"] == "EDA_UNAVAILABLE"
    assert res["base_url"] == "http://bridge.test"


def test_bridge_rescans_after_discovered_port_stops(monkeypatch):
    client = BridgeClient(port_range=range(49620, 49622))
    client._resolved = "http://127.0.0.1:49620"
    monkeypatch.setattr(client, "_probe", lambda url: url.endswith(":49621"))

    assert client.resolve_base_url() == "http://127.0.0.1:49621"


def test_get_part_enriches_device_with_symbol_pins():
    symbol_source = "\n".join(
        [
            '{"type":"PIN","id":"p1"}||{"partId":"U.1","electric":0}|',
            '{"type":"ATTR"}||{"parentId":"p1","key":"Pin Name","value":"VCC"}|',
            '{"type":"ATTR"}||{"parentId":"p1","key":"Pin Number","value":"2"}|',
            '{"type":"ATTR"}||{"parentId":"p1","key":"Pin Type","value":"Power"}|',
        ]
    )
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("part.elibu", symbol_source)
    encoded_archive = base64.b64encode(archive_buffer.getvalue()).decode()

    class FakeClient:
        def __init__(self):
            self.responses = [
                {
                    "ok": True,
                    "result": {
                        "uuid": "device-1",
                        "association": {
                            "symbol": {"uuid": "symbol-1", "libraryUuid": "library-1"}
                        },
                    },
                },
                {"ok": True, "result": encoded_archive},
            ]

        def execute(self, code):
            return self.responses.pop(0)

    res = tools.get_part(FakeClient(), "device-1", "library-1")

    assert res["ok"] is True
    assert res["result"]["pins"] == [
        {"number": "2", "name": "VCC", "type": "Power", "part": "U.1"}
    ]
    assert res["result"]["pinSource"]["symbolUuid"] == "symbol-1"
    assert res["board_spec_definition"]["pins"] == [
        {"number": "2", "name": "VCC", "type": "unspecified"}
    ]
    assert res["board_spec_definition"]["source"]["raw_pin_types"] == {"2": "Power"}
    assert res["board_spec_definition"]["review"] == {
        "status": "unreviewed",
        "pin_type_authority": "source_library",
    }


def test_get_part_definition_uses_source_metadata_and_footprint():
    symbol_source = "\n".join(
        [
            '{"type":"PIN","id":"p1"}||{"partId":"R.1","electric":0}|',
            '{"type":"ATTR"}||{"parentId":"p1","key":"Pin Name","value":"1"}|',
            '{"type":"ATTR"}||{"parentId":"p1","key":"Pin Number","value":"1"}|',
            '{"type":"ATTR"}||{"parentId":"p1","key":"Pin Type","value":"Passive"}|',
        ]
    )
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("part.elibu", symbol_source)
    encoded_archive = base64.b64encode(archive_buffer.getvalue()).decode()

    class FakeClient:
        def __init__(self):
            self.responses = [
                {
                    "ok": True,
                    "result": {
                        "uuid": "device-1",
                        "libraryUuid": "library-1",
                        "name": "R100",
                        "description": "100 ohm resistor",
                        "property": {
                            "designator": "R?",
                            "supplier": "LCSC",
                            "supplierId": "C1",
                            "manufacturer": "Vendor",
                            "manufacturerId": "R100",
                        },
                        "association": {
                            "symbol": {"uuid": "symbol-1", "libraryUuid": "library-1"},
                            "footprint": {
                                "uuid": "footprint-1",
                                "libraryUuid": "library-1",
                            },
                        },
                    },
                },
                {"ok": True, "result": encoded_archive},
                {"ok": True, "result": {"name": "R_0402"}},
            ]

        def execute(self, code):
            return self.responses.pop(0)

    res = tools.get_part(FakeClient(), "device-1", "library-1")

    definition = res["board_spec_definition"]
    assert definition["reference_prefix"] == "R"
    assert definition["footprint"] == "R_0402"
    assert definition["pins"][0]["type"] == "passive"
    assert definition["source"]["supplier_id"] == "C1"
    assert definition["source"]["footprint_uuid"] == "footprint-1"
    assert definition["source"]["device_name"] == "R100"
    assert definition["source"]["symbol_name"] == "R100"


def test_project_component_readback_requires_unique_match():
    class FakeClient:
        def execute(self, code):
            return {"ok": True, "result": []}

    res = tools.get_project_component(FakeClient(), "U1")

    assert res["ok"] is False
    assert res["code"] == "COMPONENT_NOT_FOUND"


def test_get_netlist_uses_read_api():
    class FakeClient:
        def __init__(self):
            self.code = ""

        def execute(self, code):
            self.code = code
            return {"ok": True, "result": "PROTEL NETLIST 2.0"}

    client = FakeClient()
    res = tools.get_netlist(client, "PROTEL2")

    assert res["ok"] is True
    assert res["netlist_type"] == "PROTEL2"
    assert res["document_kind"] == "schematic"
    assert "sch_Netlist" in client.code
    assert "getNetlist(\"Protel2\")" in client.code


def test_get_pcb_netlist_uses_pcb_read_api():
    class FakeClient:
        def __init__(self):
            self.code = ""

        def execute(self, code):
            self.code = code
            return {"ok": True, "result": "PROTEL NETLIST 2.0"}

    client = FakeClient()
    res = tools.get_netlist(client, "PROTEL2", "pcb")

    assert res["ok"] is True
    assert res["document_kind"] == "pcb"
    assert "pcb_Net" in client.code


def test_set_no_connects_defaults_to_preview():
    class FakeClient:
        def __init__(self):
            self.code = ""

        def execute(self, code):
            self.code = code
            return {
                "ok": True,
                "result": {
                    "matchCount": 1,
                    "requested": ["#2"],
                    "found": ["#2"],
                    "before": [{"number": "2", "noConnected": False}],
                    "after": [{"number": "2", "noConnected": False}],
                },
            }

    client = FakeClient()
    res = tools.set_no_connects(client, "U1", ["#2"])

    assert res["ok"] is True
    assert res["preview"] is True
    assert res["applied"] is False
    assert "const shouldApply = false" in client.code


def test_set_no_connects_rejects_non_exact_selector():
    res = tools.set_no_connects(object(), "U1", ["PA5"])

    assert res["ok"] is False
    assert res["code"] == "INVALID_PIN_SELECTOR"


def test_schematic_drc_reports_passed_from_empty_result():
    class FakeClient:
        def execute(self, code):
            assert "sch_Drc.check(true, false, true)" in code
            return {"ok": True, "result": []}

    res = tools.run_schematic_drc(FakeClient())

    assert res["passed"] is True


def test_pcb_drc_reports_violations():
    violations = [{"type": "Unrouted", "message": "example"}]

    class FakeClient:
        def execute(self, code):
            assert "pcb_Drc.check(true, false, true)" in code
            return {"ok": True, "result": violations}

    res = tools.run_pcb_drc(FakeClient())

    assert res["passed"] is False
    assert res["result"] == violations


def test_load_netlist_uses_runtime_string_value():
    class FakeClient:
        def __init__(self):
            self.code = None

        def execute(self, code):
            self.code = code
            return {"ok": True, "result": True}

    client = FakeClient()
    res = tools.load_netlist(client, "PROTEL NETLIST 2.0", "PROTEL2")

    assert res["ok"] is True
    assert res["staged"] is True
    assert res["requires_user_confirmation"] is True
    assert res["document_kind"] == "pcb"
    assert "ESYS_NetlistType" not in client.code
    assert "pcb_Net.setNetlist" in client.code
    assert 'setNetlist("Protel2", ' in client.code
    assert "\\r\\n" in client.code
