"""Tests for compact layout snapshots and checked EasyEDA writes."""

from __future__ import annotations

import copy

from boardspec_mcp import layout_tools
from boardspec_mcp.layout_codec import columnar, layout_revision
from boardspec_mcp.layout_drc import drc_delta, flatten_drc


def sample_state(x=100):
    return {
        "document": {"uuid": "pcb-1", "name": "Demo", "type": "pcb"},
        "layers": [
            {
                "id": 1,
                "name": "Top",
                "type": "SIGNAL",
                "layerStatus": 1,
                "locked": False,
            },
            {
                "id": 2,
                "name": "Bottom",
                "type": "SIGNAL",
                "layerStatus": 1,
                "locked": False,
            },
            {
                "id": 11,
                "name": "BoardOutline",
                "type": "OTHER",
                "layerStatus": 1,
                "locked": False,
            },
        ],
        "stacking": {"name": "2 layer", "layerCount": 2, "list": []},
        "rules": {"name": "default", "config": {}},
        "net_classes": [{"name": "Default", "nets": ["N1"], "color": None}],
        "differential_pairs": [],
        "nets": [{"net": "N1", "length": 10, "color": None}],
        "components": [
            {
                "id": "component-u1",
                "designator": "U1",
                "name": "MCU",
                "footprint": {"uuid": "fp-u1"},
                "layer": 1,
                "x": x,
                "y": 100,
                "rotation": 0,
                "locked": False,
                "bbox": {"minX": x - 10, "minY": 90, "maxX": x + 10, "maxY": 110},
                "pads": [
                    {
                        "id": "pad-u1-1",
                        "number": "1",
                        "net": "N1",
                        "layer": 1,
                        "x": x - 5,
                        "y": 100,
                        "rotation": 0,
                        "bbox": {"minX": x - 6, "minY": 99, "maxX": x - 4, "maxY": 101},
                    }
                ],
                "pad_nets": [],
            },
            {
                "id": "component-r1",
                "designator": "R1",
                "name": "R",
                "footprint": {"uuid": "fp-r"},
                "layer": 1,
                "x": 200,
                "y": 100,
                "rotation": 0,
                "locked": False,
                "bbox": {"minX": 195, "minY": 95, "maxX": 205, "maxY": 105},
                "pads": [
                    {
                        "id": "pad-r1-1",
                        "number": "1",
                        "net": "N1",
                        "layer": 2,
                        "x": 195,
                        "y": 100,
                        "rotation": 0,
                        "bbox": {"minX": 194, "minY": 99, "maxX": 196, "maxY": 101},
                    }
                ],
                "pad_nets": [],
            },
        ],
        "lines": [
            {
                "id": "outline-1",
                "net": "",
                "layer": 11,
                "start_x": 0,
                "start_y": 0,
                "end_x": 300,
                "end_y": 0,
                "width": 1,
                "locked": False,
            },
            {
                "id": "trace-1",
                "net": "N1",
                "layer": 1,
                "start_x": 95,
                "start_y": 100,
                "end_x": 105,
                "end_y": 100,
                "width": 8,
                "locked": False,
            },
        ],
        "arcs": [],
        "vias": [],
        "polylines": [],
        "pours": [],
        "poured": [],
        "regions": [],
        "obstacles": [],
    }


def drc_item(source_id="err1", net="N1"):
    return {
        "name": "Connection Error",
        "list": [
            {
                "errorType": "Connection Error",
                "errorObjType": "SMD Pad",
                "ruleName": "Common",
                "net": net,
                "objs": ["pad-u1-1"],
                "globalIndex": source_id,
                "pos": {"x": 95, "y": 100},
                "explanation": {"str": "pad is disconnected"},
            }
        ],
    }


class FakeClient:
    def __init__(self, states, drcs=None, mutation=None):
        self.states = list(states)
        self.drcs = list(drcs or [[]])
        self.mutation = (
            mutation if mutation is not None else [{"ok": True, "id": "changed"}]
        )
        self.calls = []

    def execute(self, code):
        self.calls.append(code)
        if "componentsRaw" in code:
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            return {"ok": True, "result": copy.deepcopy(state)}
        if "pcb_Drc.check(true, false, true)" in code:
            result = self.drcs.pop(0) if len(self.drcs) > 1 else self.drcs[0]
            return {"ok": True, "result": copy.deepcopy(result)}
        return {"ok": True, "result": copy.deepcopy(self.mutation)}


def test_revision_is_order_independent_and_changes_with_layout():
    state = sample_state()
    reordered = copy.deepcopy(state)
    reordered["components"].reverse()
    assert layout_revision(state) == layout_revision(reordered)
    assert layout_revision(state) != layout_revision(sample_state(x=101))


def test_columnar_keeps_explicit_schema():
    assert columnar([{"x": 1, "y": 2}], ["x", "y"]) == {
        "fields": ["x", "y"],
        "rows": [[1, 2]],
    }


def test_drc_normalization_and_delta_ignore_source_index():
    first = flatten_drc([drc_item("err1")])
    second = flatten_drc([drc_item("err99")])
    assert first[0]["id"] == second[0]["id"]
    assert first[0]["source_id"] == "err1"
    assert drc_delta(first, second) == {
        "before_count": 1,
        "new": [],
        "resolved": [],
        "remaining_count": 1,
    }


def test_drc_string_result_is_not_mistaken_for_a_pass():
    rows = flatten_drc(["board outline is open"])
    assert len(rows) == 1
    assert rows[0]["type"] == "EDA DRC"
    assert rows[0]["message"] == "board outline is open"


def test_drc_leaf_metadata_strings_are_not_extra_violations():
    item = drc_item()
    item["list"][0]["metadata"] = ["SMD Pad"]
    rows = flatten_drc([item])
    assert len(rows) == 1
    assert rows[0]["type"] == "Connection Error"


def test_summary_is_columnar_paginated_and_reports_drc_facts():
    client = FakeClient([sample_state()], drcs=[[drc_item()]])
    result = layout_tools.get_layout_summary(client, page_size=1)
    assert result["ok"] is True
    assert result["unit"] == "mil"
    assert result["components"]["fields"][0] == "designator"
    assert len(result["components"]["rows"]) == 1
    assert result["next_cursor"] == 1
    assert result["facts"]["violations_by_type"] == {"Connection Error": 1}


def test_component_detail_can_include_exact_pads():
    result = layout_tools.get_layout_components(
        FakeClient([sample_state()]), ["U1"], include_pads=True
    )
    assert result["ok"] is True
    assert result["pads"]["fields"][2:5] == ["number", "net", "layer"]
    assert result["pads"]["rows"][0][2:5] == ["1", 0, 1]
    assert result["dicts"]["nets"] == ["N1"]


def test_stale_revision_prevents_any_drc_or_mutation():
    client = FakeClient([sample_state()])
    result = layout_tools.set_component_placement(
        client, "sha256:stale", [{"designator": "U1", "x": 150}]
    )
    assert result["code"] == "STALE_LAYOUT"
    assert len(client.calls) == 1


def test_relative_placement_writes_then_reads_and_checks_drc():
    before, after = sample_state(), sample_state(x=225)
    revision = layout_revision(before)
    mutation = [
        {"ok": True, "id": "component-u1", "designator": "U1", "x": 225, "y": 105}
    ]
    client = FakeClient([before, before, after], drcs=[[], []], mutation=mutation)
    result = layout_tools.set_component_placement(
        client,
        revision,
        [{"designator": "U1", "relative_to": "R1", "dx": 25, "dy": 5}],
    )
    assert result["ok"] is True
    assert result["revision_before"] != result["revision_after"]
    program = next(code for code in client.calls if "PrimitiveComponent.modify" in code)
    assert '"x": 225.0' in program and '"y": 105.0' in program
    assert sum("pcb_Drc.check" in code for code in client.calls) == 2


def test_create_route_resolves_pads_and_inserts_via_for_layer_change():
    before = sample_state()
    after = copy.deepcopy(before)
    after["vias"].append(
        {
            "id": "via-1",
            "net": "N1",
            "x": 195,
            "y": 100,
            "hole_diameter": 10,
            "diameter": 20,
            "via_type": 0,
            "blind_via_rule": None,
            "locked": False,
        }
    )
    client = FakeClient([before, before, after], drcs=[[], []])
    result = layout_tools.create_route(
        client,
        layout_revision(before),
        "N1",
        [{"start": "U1.#1", "end": "R1.#1"}],
        {"width": 8, "hole_diameter": 10, "diameter": 20},
    )
    assert result["ok"] is True
    program = next(code for code in client.calls if "PrimitiveLine.create" in code)
    assert '"type": "line"' in program
    assert '"type": "via"' in program


def test_checked_write_reports_partial_apply_and_drc_delta():
    before, after = sample_state(), sample_state(x=101)
    client = FakeClient(
        [before, after],
        drcs=[[], [drc_item()]],
        mutation=[{"ok": True, "id": "a"}, {"ok": False, "id": "b"}],
    )
    result = layout_tools._checked_write(
        client, layout_revision(before), "return true;"
    )
    assert result["ok"] is False
    assert result["partial"] is True
    assert result["code"] == "PARTIAL_APPLY"
    assert len(result["drc"]["new"]) == 1


def test_checked_write_does_not_call_all_failed_batch_partial():
    state = sample_state()
    client = FakeClient(
        [state, state],
        drcs=[[], []],
        mutation=[{"ok": False, "id": "a"}, {"ok": False, "id": "b"}],
    )
    result = layout_tools._checked_write(
        client, layout_revision(state), "return false;"
    )
    assert result["applied"] is False
    assert result["partial"] is False
    assert result["code"] == "EDA_WRITE_REJECTED"


def test_existing_outline_requires_explicit_replace():
    state = sample_state()
    result = layout_tools.set_board_outline(
        FakeClient([state]),
        layout_revision(state),
        [[{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]],
    )
    assert result["code"] == "OUTLINE_EXISTS"


def test_new_outline_uses_explicit_editor_default_width():
    state = sample_state()
    state["lines"] = [line for line in state["lines"] if line.get("layer") != 11]
    after = copy.deepcopy(state)
    after["polylines"].append(
        {
            "id": "outline-new",
            "net": "",
            "layer": 11,
            "polygon": [0, 0, "L", 10, 0, 10, 10, 0, 0],
            "width": 5,
            "locked": False,
            "bbox": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10},
        }
    )
    client = FakeClient([state, state, after], drcs=[[], []])
    result = layout_tools.set_board_outline(
        client,
        layout_revision(state),
        [[{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]],
    )
    assert result["ok"] is True
    program = next(code for code in client.calls if "PrimitivePolyline.create" in code)
    assert "?.width ?? 5" in program


def test_routing_detail_excludes_board_outline():
    result = layout_tools.get_layout_routing(FakeClient([sample_state()]))
    assert result["ok"] is True
    ids = [row[0] for row in result["lines"]["rows"]]
    assert ids == ["trace-1"]
    assert result["lines"]["rows"][0][1] == 0
    assert result["dicts"]["nets"] == ["N1"]


def test_board_geometry_separates_outline_and_obstacles():
    state = sample_state()
    state["obstacles"] = [
        {
            "id": "image-1",
            "type": "Image",
            "bbox": {"minX": 1, "minY": 1, "maxX": 2, "maxY": 2},
        }
    ]
    result = layout_tools.get_board_geometry(FakeClient([state]))
    assert result["outline"]["lines"][0]["id"] == "outline-1"
    assert result["obstacles"]["rows"][0][0] == "image-1"


def test_violation_filters_by_net():
    client = FakeClient([sample_state()], drcs=[drc_item(net="N1")])
    result = layout_tools.get_layout_violations(client, nets=["OTHER"])
    assert result["total_count"] == 1
    assert result["matched_count"] == 0
    assert result["passed"] is False


def test_auto_routing_validates_nets_before_write():
    state = sample_state()
    client = FakeClient([state])
    result = layout_tools.run_auto_routing(
        client, layout_revision(state), nets=["MISSING"]
    )
    assert result["code"] == "NET_NOT_FOUND"
    assert not any("autoRouting" in code for code in client.calls)


def test_edit_routing_maps_compact_property_names():
    state = sample_state()
    after = copy.deepcopy(state)
    after["lines"][1]["width"] = 12
    client = FakeClient([state, state, after], drcs=[[], []])
    result = layout_tools.edit_routing(
        client,
        layout_revision(state),
        [
            {
                "op": "modify",
                "type": "line",
                "id": "trace-1",
                "properties": {"width": 12},
            }
        ],
    )
    assert result["ok"] is True
    program = next(code for code in client.calls if "const apis" in code)
    assert '"lineWidth": 12' in program


def test_keepout_create_maps_to_region_api_and_checks_drc():
    state = sample_state()
    after = copy.deepcopy(state)
    after["regions"] = [{"id": "region-1", "layer": 1, "polygon": [0, 0, "L", 1, 1]}]
    client = FakeClient([state, state, after], drcs=[[], []])
    result = layout_tools.edit_keepouts(
        client,
        layout_revision(state),
        [{"op": "create", "polygon": [0, 0, "L", 1, 1], "layer": 1, "rule_types": [5]}],
    )
    assert result["ok"] is True
    assert any("PrimitiveRegion.create" in code for code in client.calls)


def test_pour_create_requires_existing_net():
    state = sample_state()
    result = layout_tools.edit_copper_pours(
        FakeClient([state]),
        layout_revision(state),
        [{"op": "create", "polygon": [0, 0, "L", 1, 1], "layer": 1, "net": "NOPE"}],
    )
    assert result["code"] == "NET_NOT_FOUND"


def test_pour_rebuild_uses_instance_api():
    state = sample_state()
    after = copy.deepcopy(state)
    after["pours"] = [
        {
            "id": "pour-1",
            "net": "N1",
            "layer": 2,
            "polygon": ["R", 0, 0, 10, 10, 0, 0],
        }
    ]
    client = FakeClient([state, state, after], drcs=[[], []])
    result = layout_tools.edit_copper_pours(
        client,
        layout_revision(state),
        [
            {
                "op": "create",
                "polygon": ["R", 0, 0, 10, 10, 0, 0],
                "layer": 2,
                "net": "N1",
            }
        ],
        rebuild=True,
    )
    assert result["ok"] is True
    program = next(code for code in client.calls if "PrimitivePour.create" in code)
    assert "pcb_PrimitivePour.get(id)" in program
    assert "pour.rebuildCopperRegion()" in program
    assert "rebuildCopperRegions" not in program


def test_keepout_modify_allows_property_only_and_rejects_unavailable_layer():
    state = sample_state()
    state["regions"] = [{"id": "region-1", "layer": 1, "polygon": ["R", 1, 1, 2, 2]}]
    after = copy.deepcopy(state)
    after["regions"][0]["name"] = "renamed"
    client = FakeClient([state, state, after], drcs=[[], []])
    result = layout_tools.edit_keepouts(
        client,
        layout_revision(state),
        [{"op": "modify", "id": "region-1", "name": "renamed"}],
    )
    assert result["ok"] is True
    assert result["readback"]["changes"]["regions"]["modified"][0]["name"] == "renamed"

    invalid = layout_tools.edit_keepouts(
        FakeClient([state]),
        layout_revision(state),
        [{"op": "modify", "id": "region-1", "layer": 99}],
    )
    assert invalid["code"] == "INVALID_LAYER"


def test_routing_modify_rejects_wrong_primitive_properties_before_write():
    state = sample_state()
    client = FakeClient([state])
    result = layout_tools.edit_routing(
        client,
        layout_revision(state),
        [{"op": "modify", "type": "line", "id": "trace-1", "properties": {"x": 3}}],
    )
    assert result["code"] == "INVALID_EDIT"
    assert not any("const apis" in code for code in client.calls)


def test_violation_region_uses_eda_position_object():
    result = layout_tools.get_layout_violations(
        FakeClient([sample_state()], drcs=[drc_item()]),
        region={"left": 900, "right": 1000, "bottom": 900, "top": 1100},
    )
    assert result["matched_count"] == 1


def test_drc_positions_are_normalized_to_mil_and_group_labels_are_ignored():
    rows = flatten_drc(["Connection Error", [drc_item()]])
    assert len(rows) == 1
    assert rows[0]["position"] == {"x": 950, "y": 1000}


def test_mcp_write_tools_publish_explicit_nested_schemas():
    from boardspec_mcp.server import mcp

    schema = mcp._tool_manager._tools["create_route"].parameters
    assert schema["properties"]["branches"]["items"]["$ref"].endswith("RouteBranch")
    placement = mcp._tool_manager._tools["set_component_placement"].parameters
    assert placement["properties"]["edits"]["items"]["$ref"].endswith("PlacementEdit")
