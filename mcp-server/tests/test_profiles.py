"""Contracts for the focused MCP profiles and distributable plugin."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from boardspec_mcp import server
from boardspec_mcp.core_server import mcp as core_mcp
from boardspec_mcp.layout_server import mcp as layout_mcp
from boardspec_mcp.profiles import CORE_TOOLS, LAYOUT_TOOLS, SCHEMATIC_LEGACY_TOOLS
from boardspec_mcp.schematic_entry import mcp as schematic_mcp

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "quick-pcb"

SCHEMATIC_PROFILE_TOOLS = {
    "get_eda_windows",
    "get_schematic_context",
    "create_project",
    "open_project",
    "create_schematic",
    "create_schematic_page",
    "open_schematic_page",
    "save_schematic",
    "get_schematic_summary",
    "get_schematic_components",
    "get_schematic_wiring",
    "get_schematic_violations",
    "plan_schematic",
    "resolve_schematic_plan",
    "diff_schematic_plan",
    "verify_schematic_topology",
    "verify_schematic_readability",
    "place_schematic_components",
    "set_schematic_component_placement",
    "remove_schematic_components",
    "create_schematic_wires",
    "edit_schematic_wires",
    "place_schematic_net_labels",
    "place_schematic_net_ports",
    "place_schematic_net_flags",
    "edit_schematic_net_markers",
    "set_schematic_no_connects",
}

LAYOUT_WRITES = {
    "load_netlist",
    "set_component_placement",
    "run_auto_layout",
    "create_route",
    "edit_routing",
    "run_auto_routing",
    "set_board_outline",
    "edit_keepouts",
    "edit_copper_pours",
}

SCHEMATIC_WRITES = {
    "set_no_connects",
    "create_project",
    "open_project",
    "create_schematic",
    "create_schematic_page",
    "open_schematic_page",
    "save_schematic",
    "place_schematic_components",
    "set_schematic_component_placement",
    "remove_schematic_components",
    "create_schematic_wires",
    "edit_schematic_wires",
    "place_schematic_net_labels",
    "place_schematic_net_ports",
    "place_schematic_net_flags",
    "edit_schematic_net_markers",
    "set_schematic_no_connects",
}


def _names(mcp):
    return {tool.name for tool in mcp._tool_manager.list_tools()}


def test_profiles_publish_exact_tool_surfaces():
    assert _names(core_mcp) == set(CORE_TOOLS)
    assert _names(layout_mcp) == set(LAYOUT_TOOLS)
    assert _names(schematic_mcp) == set(SCHEMATIC_LEGACY_TOOLS) | SCHEMATIC_PROFILE_TOOLS
    assert len(_names(server.mcp)) == 53


@pytest.mark.parametrize(
    ("mcp", "name"),
    [
        (core_mcp, "boardspec-core"),
        (layout_mcp, "boardspec-layout"),
        (schematic_mcp, "boardspec-schematic"),
    ],
)
def test_profiles_publish_metadata_schemas_and_annotations(mcp, name):
    assert mcp.name == name
    assert mcp.version == "0.3.1"
    assert mcp.instructions
    for tool in mcp._tool_manager.list_tools():
        assert tool.output_schema is not None
        assert tool.annotations is not None
        assert tool.annotations.open_world_hint is False


def test_core_schema_has_base_dir_and_enum_target():
    tools = {tool.name: tool for tool in core_mcp._tool_manager.list_tools()}
    assert "base_dir" in tools["validate"].parameters["properties"]
    assert {"ok", "errors", "warnings"} <= set(
        tools["validate"].output_schema["properties"]
    )
    assert "expanded_spec" in tools["expand"].output_schema["properties"]
    assert "content" in tools["export"].output_schema["properties"]
    target = tools["export"].parameters["properties"]["target"]
    assert set(target["enum"]) == {
        "protel2_netlist",
        "kicad_netlist",
        "bom_csv",
        "mermaid",
    }


def test_eda_output_schemas_publish_context_and_revision_fields():
    layout = {tool.name: tool for tool in layout_mcp._tool_manager.list_tools()}
    schematic = {tool.name: tool for tool in schematic_mcp._tool_manager.list_tools()}
    assert {"document", "revision", "counts"} <= set(
        layout["get_layout_summary"].output_schema["properties"]
    )
    assert {"source", "context_revision", "revision"} <= set(
        schematic["get_schematic_context"].output_schema["properties"]
    )


def test_bridge_status_is_structured_but_other_transport_failures_are_errors(monkeypatch):
    class Offline:
        def health(self):
            return {"ok": False, "code": "BRIDGE_UNAVAILABLE", "message": "offline"}

        def execute(self, code):
            return {"ok": False, "code": "BRIDGE_UNAVAILABLE", "message": "offline"}

    monkeypatch.setattr(server, "client", Offline())
    status = server.bridge_status()
    assert status.ok is False
    assert status.code == "BRIDGE_UNAVAILABLE"
    with pytest.raises(ToolError, match="BRIDGE_UNAVAILABLE"):
        server.search_part("STM32")


def test_invalid_netlist_is_a_tool_error_before_bridge(monkeypatch):
    class UnexpectedBridgeCall:
        def execute(self, code):
            raise AssertionError("invalid input must not reach the bridge")

    monkeypatch.setattr(server, "client", UnexpectedBridgeCall())
    with pytest.raises(ToolError, match="INVALID_NETLIST"):
        server.load_netlist("PROTEL NETLIST 2.0")


def test_plugin_manifests_match_runtime_and_approval_policy():
    portable = json.loads((PLUGIN / "mcp.json").read_text())
    compat = json.loads((PLUGIN / ".mcp.json").read_text())
    expected = {"boardspec-core", "boardspec-layout", "boardspec-schematic"}
    assert set(portable["mcpServers"]) == expected
    assert set(compat["mcpServers"]) == expected
    for name in expected:
        portable_server = portable["mcpServers"][name]
        compat_server = compat["mcpServers"][name]
        assert portable_server["command"] == compat_server["command"] == "uv"
        assert portable_server["args"] == compat_server["args"]
        assert "@v0.3.1#subdirectory=mcp-server" in " ".join(portable_server["args"])
        assert compat_server["startup_timeout_sec"] == 300
    assert compat["mcpServers"]["boardspec-core"]["enabled"] is True
    assert compat["mcpServers"]["boardspec-layout"]["enabled"] is False
    assert compat["mcpServers"]["boardspec-schematic"]["enabled"] is False
    assert set(compat["mcpServers"]["boardspec-layout"]["tools"]) == LAYOUT_WRITES
    assert set(compat["mcpServers"]["boardspec-schematic"]["tools"]) == SCHEMATIC_WRITES


def test_repo_plugin_config_enables_only_core():
    config = tomllib.loads((REPO / ".codex" / "config.toml").read_text())
    plugin = config["plugins"]["quick-pcb@quick-pcb-local"]
    assert plugin["enabled"] is True
    services = plugin["mcp_servers"]
    assert services["boardspec-core"]["enabled"] is True
    assert services["boardspec-layout"]["enabled"] is False
    assert services["boardspec-schematic"]["enabled"] is False


def test_plugin_skill_matches_tracked_source_files():
    source = REPO / ".agents" / "skills" / "board-spec"
    packaged = PLUGIN / "skills" / "board-spec"

    def files(root):
        return {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
            and ".venv" not in path.parts
            and "__pycache__" not in path.parts
            and path.name != ".DS_Store"
        }

    assert files(packaged) == files(source)
