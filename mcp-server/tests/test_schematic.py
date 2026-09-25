"""Tests for deterministic schematic planning and checked EasyEDA writes."""

from __future__ import annotations

import copy
import subprocess
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from boardspec_mcp import schematic_tools
from boardspec_mcp import schematic_bridge
from boardspec_mcp.bridge_client import BridgeClient
from boardspec_mcp.schematic_codec import (
    context_revision,
    normalize_state,
    primitive_in_region,
    require_grid,
    schematic_revision,
    to_eda,
)
from boardspec_mcp.schematic_drc import flatten_schematic_drc
from boardspec_mcp.schematic_plan import build_plan, compare_topology, diff_plan
from boardspec_mcp.schematic_routing import route_orthogonal
from boardspec_mcp.schematic_types import ComponentPlacement, PlanOptions, SchematicPlan

ROOT = Path(__file__).resolve().parents[2]


def raw_state(x=1000):
    return {
        "source": {
            "project_uuid": "project-1",
            "project_name": "Demo",
            "schematic_uuid": "schematic-1",
            "schematic_name": "Main",
            "page_uuid": "page-1",
            "page_name": "p1",
            "document_uuid": "page-1",
            "document_type": 1,
            "tab_id": "tab-1",
        },
        "components": [
            {
                "id": "component-u1",
                "designator": "U1",
                "name": "MCU",
                "component": {"libraryUuid": "library-1", "uuid": "device-1"},
                "symbol": {"uuid": "symbol-1"},
                "footprint": {"uuid": "footprint-1"},
                "x": x,
                "y": 1000,
                "rotation": 0,
                "mirror": False,
                "bbox": {"minX": x - 100, "minY": 900, "maxX": x + 100, "maxY": 1100},
                "pins": [
                    {"id": "pin-2", "number": "2", "name": "B", "type": "IN", "no_connected": False, "x": x + 100, "y": 1000},
                    {"id": "pin-1", "number": "1", "name": "A", "type": "OUT", "no_connected": False, "x": x - 100, "y": 1000},
                ],
            }
        ],
        "wires": [],
        "labels": [],
        "ports": [],
        "flags": [],
        "no_connects": [],
        "nets": [],
        "netlist": "PROTEL NETLIST 2.0\n[\nU1\n\n]\n(N1\nU1-1\n)\n",
    }


class FakeClient:
    def __init__(self, before=None, after=None, mutation=None):
        self.before = before or raw_state()
        self.after = after or self.before
        self.mutation = mutation if mutation is not None else [{"ok": True, "id": "created"}]
        self.mutated = False
        self.calls = []

    def health(self):
        return {"ok": True, "active_window_id": "window-1"}

    def list_windows(self):
        return {"ok": True, "active_window_id": "window-1", "windows": [{"id": "window-1"}]}

    def execute(self, code, window_id=None):
        self.calls.append((code, window_id))
        if "const componentRaw" in code:
            return {"ok": True, "result": copy.deepcopy(self.after if self.mutated else self.before)}
        if "WINDOW" in code:
            raise AssertionError("unexpected marker")
        if "const schematicItems" in code and "componentRaw" not in code:
            return {"ok": True, "result": {**copy.deepcopy(self.before["source"]), "window_id": window_id or "window-1"}}
        if "sch_Drc.check" in code:
            return {"ok": True, "result": []}
        if "getEditorCurrentVersion" in code:
            return {"ok": True, "result": "3.2.186"}
        self.mutated = True
        if isinstance(self.mutation, dict) and self.mutation.get("ok") is False:
            return copy.deepcopy(self.mutation)
        return {"ok": True, "result": copy.deepcopy(self.mutation)}


def test_strict_models_reject_extra_fields():
    with pytest.raises(ValidationError):
        ComponentPlacement(
            client_id="p/U1", library_uuid="lib", device_uuid="dev",
            designator="U1", x=100, y=100, unexpected=True,
        )
    with pytest.raises(ValidationError):
        PlanOptions(measured_geometry={"U1": {"unknown": 1}})
    assert PlanOptions().page_policy == "single_page"


def test_coordinate_grid_and_conversion_are_explicit():
    assert to_eda(250) == 25
    assert require_grid(100) == 100
    with pytest.raises(ValueError):
        require_grid(105)


def test_revisions_are_stable_under_ordering_and_split_context():
    left = normalize_state(raw_state(), "window-1")
    right_raw = raw_state()
    right_raw["components"][0]["pins"].reverse()
    right = normalize_state(right_raw, "window-1")
    assert left["revision"] == right["revision"]
    assert left["context_revision"] == right["context_revision"]
    assert left["revision"] != schematic_revision(normalize_state(raw_state(1100), "window-1"))
    assert left["context_revision"] != context_revision({**left["source"], "window_id": "window-2"})


def test_schematic_drc_string_is_a_violation_and_id_is_stable():
    first = flatten_schematic_drc(["unconnected pin"], "page-1")
    second = flatten_schematic_drc(["unconnected pin"], "page-1")
    assert len(first) == 1
    assert first[0]["id"] == second[0]["id"]


def test_schematic_drc_normalizes_position_and_ignores_group_label():
    rows = flatten_schematic_drc(
        ["Connection Error", [{"errorType": "Open", "message": "pin", "pos": [90, 110]}]],
        "page-1",
    )
    assert len(rows) == 1
    assert rows[0]["position"] == {"x": 900, "y": 1100}
    assert primitive_in_region(
        rows[0], {"left": 850, "right": 950, "bottom": 1050, "top": 1150}
    )


def test_schematic_wiring_region_matches_crossing_segment():
    state = raw_state()
    state["wires"] = [{
        "id": "w1", "net": "N1",
        "points": [{"x": 0, "y": 1000}, {"x": 2000, "y": 1000}],
    }]
    result = schematic_tools.get_schematic_wiring(
        FakeClient(before=state), "window-1", region={
            "left": 900, "right": 1100, "bottom": 900, "top": 1100,
        }
    )
    assert [wire["id"] for wire in result["wires"]] == ["w1"]


@pytest.mark.parametrize(
    ("fixture", "base_dir", "components", "nets", "nodes"),
    [
        ("boardspec-e2e-mosfet-led.yaml", None, 11, 5, 31),
        ("boardspec-e2e-stc51-clock.yaml", str(ROOT / "examples"), 25, 21, 76),
    ],
)
def test_planner_is_deterministic_and_matches_fixture_counts(
    fixture, base_dir, components, nets, nodes, monkeypatch
):
    monkeypatch.chdir(ROOT)
    text = (ROOT / "examples" / fixture).read_text()
    options = {"base_dir": base_dir} if base_dir else None
    first, second = build_plan(text, options), build_plan(text, options)
    assert first == second
    assert first["ok"] is True
    SchematicPlan.model_validate(first["plan"])
    invalid_plan = {**first["plan"], "unexpected": True}
    with pytest.raises(ValidationError):
        SchematicPlan.model_validate(invalid_plan)
    topology = first["plan"]["topology"]
    assert len(topology["components"]) == components
    assert len(topology["nets"]) == nets
    assert sum(len(value) for value in topology["nets"].values()) == nodes
    assert all(item["identification"] in {"Power", "Ground"} for item in first["plan"]["flags"])


def test_second_pass_layout_uses_anchor_relative_geometry_without_overlap(monkeypatch):
    monkeypatch.chdir(ROOT)
    text = (ROOT / "examples" / "boardspec-e2e-mosfet-led.yaml").read_text()
    geometry = {
        "R2": {"min_dx": -105, "max_dx": 105, "min_dy": -45, "max_dy": 45},
        "U1": {"min_dx": -755, "max_dx": 755, "min_dy": -1255, "max_dy": 1255},
    }
    plan = build_plan(text, {"measured_geometry": geometry})["plan"]
    placed = {item["designator"]: item for item in plan["placements"]}
    r2, u1 = placed["R2"], placed["U1"]
    r2_box = (r2["x"] - 105, r2["y"] - 45, r2["x"] + 105, r2["y"] + 45)
    u1_box = (u1["x"] - 755, u1["y"] - 1255, u1["x"] + 755, u1["y"] + 1255)
    assert r2_box[2] + 400 <= u1_box[0]
    assert all(value % 100 == 0 for item in placed.values() for value in (item["x"], item["y"]))


def test_planner_can_use_v3_net_ports_for_high_fanout(monkeypatch):
    monkeypatch.chdir(ROOT)
    text = (ROOT / "examples" / "boardspec-e2e-mosfet-led.yaml").read_text()
    plan = build_plan(text, {"high_fanout_primitive": "port"})["plan"]
    assert plan["labels"] == []
    assert len(plan["ports"]) == 3
    assert {item["net"] for item in plan["ports"]} == {"LED_CTRL"}


def test_plan_diff_reports_create_move_conflict_and_extra():
    plan = {
        "format": "schematic-plan/v0.1",
        "placements": [
            {"designator": "U1", "library_uuid": "library-1", "device_uuid": "device-1", "x": 1200, "y": 1000, "rotation": 0, "mirror": False},
            {"designator": "R1", "library_uuid": "library-1", "device_uuid": "device-r", "x": 2000, "y": 1000, "rotation": 0, "mirror": False},
        ],
        "topology": {"components": ["R1", "U1"], "nets": {"N1": [["R1", "1"], ["U1", "1"]]}},
    }
    state = normalize_state(raw_state(), "window-1")
    state["components"].append({"id": "x", "designator": "X1", "component": {}})
    result = diff_plan(plan, state)
    assert [item["designator"] for item in result["create"]] == ["R1"]
    assert [item["designator"] for item in result["move"]] == ["U1"]
    assert result["extra"][0]["designator"] == "X1"


def test_topology_compare_detects_missing_and_extra_nodes():
    expected = "PROTEL NETLIST 2.0\n[\nU1\n\n]\n(\nN1\nU1-1\n)\n"
    actual = "PROTEL NETLIST 2.0\n[\nU1\n\n]\n(\nN1\nU1-2\n)\n"
    result = compare_topology(expected, actual)
    assert result["ok"] is False
    assert result["missing"] == {"N1": [["U1", "1"]]}
    assert result["extra"] == {"N1": [["U1", "2"]]}


def test_stale_revision_prevents_drc_and_mutation():
    client = FakeClient()
    result = schematic_tools.set_schematic_component_placement(
        client, "window-1", "sha256:wrong-context", "sha256:wrong", [{"designator": "U1", "x": 1200}]
    )
    assert result["code"] == "CONTEXT_CHANGED"
    assert all("sch_Drc.check" not in code for code, _ in client.calls)
    assert all("PrimitiveComponent.modify" not in code for code, _ in client.calls)


def test_write_timeout_becomes_unknown_and_is_not_retried():
    before = normalize_state(raw_state(), "window-1")
    client = FakeClient(mutation={"ok": False, "code": "BRIDGE_TIMEOUT", "message": "late"})
    result = schematic_tools.set_schematic_component_placement(
        client, "window-1", before["context_revision"], before["revision"], [{"designator": "U1", "x": 1200}]
    )
    assert result["code"] == "WRITE_STATUS_UNKNOWN"
    assert sum("PrimitiveComponent.modify" in code for code, _ in client.calls) == 1


def test_write_http_500_becomes_unknown_and_is_not_retried():
    before = normalize_state(raw_state(), "window-1")
    client = FakeClient(mutation={"ok": False, "code": "BRIDGE_HTTP_ERROR", "status_code": 500, "message": "late"})
    result = schematic_tools.set_schematic_component_placement(
        client, "window-1", before["context_revision"], before["revision"], [{"designator": "U1", "x": 1200}]
    )
    assert result["code"] == "WRITE_STATUS_UNKNOWN"
    assert sum("PrimitiveComponent.modify" in code for code, _ in client.calls) == 1


def test_wire_creation_resolves_pin_and_routes_around_component_body():
    after = raw_state()
    after["wires"] = [{"id": "w1", "net": "N1", "points": [{"x": 900, "y": 1000}, {"x": 2000, "y": 1000}, {"x": 2000, "y": 1600}]}]
    client = FakeClient(after=after)
    before = normalize_state(raw_state(), "window-1")
    result = schematic_tools.create_schematic_wires(
        client, "window-1", before["context_revision"], before["revision"],
        [{"net": "N1", "branches": [{"client_id": "plan/N1/0", "start": "U1.#1", "end": {"x": 2000, "y": 1600}, "waypoints": []}]}],
    )
    assert result["ok"] is True
    program = next(code for code, _ in client.calls if "PrimitiveWire.create" in code)
    assert "[90.0,100.0],[90.0,160.0],[200.0,160.0]" in program
    assert "expectedContext" in program


def test_net_labels_fail_fast_on_easyeda_v3_without_mutation():
    client = FakeClient()
    before = normalize_state(raw_state(), "window-1")
    result = schematic_tools.place_schematic_net_labels(
        client, "window-1", before["context_revision"], before["revision"],
        [{"client_id": "label-1", "net": "N1", "at": "U1.#1", "rotation": 0, "mirror": False}],
    )
    assert result["code"] == "API_UNAVAILABLE"
    assert result["editor_version"] == "3.2.186"
    assert all("createNetLabel" not in code for code, _ in client.calls)


def test_marker_program_converts_rotation_at_easyeda_api_boundary():
    created = schematic_bridge.marker_program("port", [{
        "client_id": "p", "net": "N", "direction": "BI",
        "x": 100, "y": 200, "rotation": 270,
    }])
    edited = schematic_bridge.marker_edit_program([{
        "op": "replace", "kind": "flag", "id": "old",
        "replacement": {
            "kind": "flag", "client_id": "f", "net": "GND",
            "at": {"x": 100, "y": 200}, "rotation": 90,
            "identification": "Ground",
        },
    }])
    assert '"rotation":90' in created
    assert '"rotation":270' in edited


def test_wire_edit_program_uses_flat_easyeda_line_coordinates():
    program = schematic_bridge.wire_edit_program([{
        "op": "modify", "id": "wire-1",
        "properties": {"points": [{"x": 100, "y": 200}, {"x": 300, "y": 200}]},
    }])
    assert '"line":[10.0,20.0,30.0,20.0]' in program


def test_router_avoids_unrelated_pins_and_existing_wires():
    components = [{"bbox": {"minX": 400, "minY": 400, "maxX": 600, "maxY": 600},
                   "pins": [{"x": 300, "y": 500}]}]
    existing = [{"points": [{"x": 0, "y": 700}, {"x": 1000, "y": 700}]}]
    route = route_orthogonal([{"x": 0, "y": 500}, {"x": 1000, "y": 500}], components, existing)
    assert route is not None
    assert all(not (a["y"] == b["y"] == 500 and min(a["x"], b["x"]) <= 300 <= max(a["x"], b["x"])) for a, b in zip(route, route[1:]))
    assert all(not (a["y"] == b["y"] == 700) for a, b in zip(route, route[1:]))


def test_all_generated_javascript_passes_node_check(tmp_path):
    placement = {"client_id": "p/U1", "library_uuid": "lib", "device_uuid": "dev", "designator": "U1", "x": 100, "y": 100}
    programs = [
        schematic_bridge.CAPTURE_SCHEMATIC_JS, schematic_bridge.WINDOW_CONTEXT_JS,
        schematic_bridge.CAPABILITY_PROBE_JS,
        schematic_bridge.create_project_program("friendly", "project", "description"),
        schematic_bridge.open_project_program("project"), schematic_bridge.create_schematic_program("Main"),
        schematic_bridge.create_page_program("schematic", "P2"), schematic_bridge.open_page_program("page"),
        schematic_bridge.save_program(), schematic_bridge.component_create_program([placement]),
        schematic_bridge.component_edit_program([{"id": "id", "designator": "U1", "properties": {"x": 200}}]),
        schematic_bridge.component_remove_program(["id"]),
        schematic_bridge.wire_create_program([{"client_id": "w", "net": "N", "points": [{"x": 0, "y": 0}, {"x": 100, "y": 0}]}]),
        schematic_bridge.wire_edit_program([{"op": "delete", "id": "w", "properties": {}}]),
        schematic_bridge.marker_program("port", [{"client_id": "p", "net": "N", "direction": "BI", "x": 0, "y": 0}]),
        schematic_bridge.marker_program("flag", [{"client_id": "f", "net": "GND", "identification": "Ground", "x": 0, "y": 0}]),
        schematic_bridge.marker_program("label", [{"client_id": "l", "net": "N", "x": 0, "y": 0}]),
        schematic_bridge.marker_edit_program([{
            "op": "replace", "kind": "port", "id": "old",
            "replacement": {"kind": "port", "client_id": "p", "net": "N", "at": {"x": 100, "y": 0}, "direction": "BI"},
        }]),
        schematic_bridge.no_connect_program([{"designator": "U1", "pin_selectors": ["#1"]}]),
        schematic_bridge.guarded_program(raw_state()["source"], "return true;", normalize_state(raw_state(), "window-1")),
    ]
    for index, program in enumerate(programs):
        path = tmp_path / f"program-{index}.js"
        path.write_text(f"async function generated() {{\n{program}\n}}\n")
        subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, text=True)


def test_project_creation_refuses_an_active_document():
    client = FakeClient()
    result = schematic_tools.create_project(client, "window-1", "Disposable")
    assert result["code"] == "DOCUMENT_SWITCH_UNSAFE"
    assert all("createProject" not in code for code, _ in client.calls)


def test_start_page_is_not_treated_as_a_design_document():
    assert schematic_tools._active_document(
        {"document_uuid": "tab_page1", "document_type": -1}
    ) is False


def test_bridge_client_targets_window_and_lists_without_selecting(monkeypatch):
    requests = []

    def fake_get(url, timeout):
        request = httpx.Request("GET", url)
        if url.endswith("/eda-windows"):
            return httpx.Response(200, request=request, json={"activeWindowId": "w1", "windows": [{"id": "w1"}]})
        return httpx.Response(200, request=request, json={"service": "easyeda-bridge"})

    def fake_post(url, json, timeout):
        requests.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url), json={"type": "result", "result": 1})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = BridgeClient("http://bridge.invalid")
    assert client.list_windows()["windows"][0]["id"] == "w1"
    assert client.execute("return 1", "w1")["ok"] is True
    assert requests == [{"code": "return 1", "windowId": "w1"}]


def test_stale_target_window_is_rejected_before_execute():
    client = FakeClient()
    client.list_windows = lambda: {
        "ok": True, "active_window_id": "window-2",
        "windows": [{"id": "window-2", "connected": True}],
    }
    result = schematic_tools.get_schematic_context(client, "window-1")
    assert result["code"] == "EDA_WINDOW_UNAVAILABLE"
    assert client.calls == []


def test_server_registers_all_schematic_tools():
    from boardspec_mcp.server import mcp

    names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert len(names) == 53
    assert {
        "plan_schematic", "resolve_schematic_plan", "create_schematic_wires",
        "edit_schematic_net_markers", "verify_schematic_readability",
        "save_schematic",
    } <= names
