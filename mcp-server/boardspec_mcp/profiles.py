"""Build the focused Core, Layout, and Schematic MCP profiles."""

from __future__ import annotations

from . import server as full
from .bridge_client import BridgeClient
from .protocol import (
    READ_ONLY,
    WRITE_ADD,
    WRITE_DESTRUCTIVE,
    WRITE_SET,
    make_server,
)
from .schematic_server import register_schematic_tools

CORE_TOOLS = ("validate", "expand", "export")

LAYOUT_TOOLS = (
    "bridge_status",
    "search_part",
    "get_part",
    "get_netlist",
    "run_pcb_drc",
    "load_netlist",
    "get_layout_summary",
    "get_layout_components",
    "get_layout_routing",
    "get_board_geometry",
    "get_layout_rules",
    "get_layout_violations",
    "set_component_placement",
    "run_auto_layout",
    "create_route",
    "edit_routing",
    "run_auto_routing",
    "set_board_outline",
    "edit_keepouts",
    "edit_copper_pours",
)

SCHEMATIC_LEGACY_TOOLS = (
    "bridge_status",
    "search_part",
    "get_part",
    "get_project_component",
    "get_netlist",
    "set_no_connects",
    "run_schematic_drc",
)

_ANNOTATIONS = {
    **{name: READ_ONLY for name in CORE_TOOLS},
    **{
        name: READ_ONLY
        for name in (
            "bridge_status",
            "search_part",
            "get_part",
            "get_project_component",
            "get_netlist",
            "run_schematic_drc",
            "run_pcb_drc",
            "get_layout_summary",
            "get_layout_components",
            "get_layout_routing",
            "get_board_geometry",
            "get_layout_rules",
            "get_layout_violations",
        )
    },
    "set_no_connects": WRITE_DESTRUCTIVE,
    "load_netlist": WRITE_DESTRUCTIVE,
    "set_component_placement": WRITE_SET,
    "run_auto_layout": WRITE_DESTRUCTIVE,
    "create_route": WRITE_ADD,
    "edit_routing": WRITE_DESTRUCTIVE,
    "run_auto_routing": WRITE_DESTRUCTIVE,
    "set_board_outline": WRITE_DESTRUCTIVE,
    "edit_keepouts": WRITE_DESTRUCTIVE,
    "edit_copper_pours": WRITE_DESTRUCTIVE,
}


def _register_existing(target, names: tuple[str, ...]) -> None:
    for name in names:
        target.tool(
            name=name,
            annotations=_ANNOTATIONS[name],
            structured_output=True,
        )(getattr(full, name))


def create_core_server():
    mcp = make_server("core")
    _register_existing(mcp, CORE_TOOLS)
    return mcp


def create_layout_server():
    mcp = make_server("layout")
    _register_existing(mcp, LAYOUT_TOOLS)
    return mcp


def create_schematic_server():
    mcp = make_server("schematic")
    _register_existing(mcp, SCHEMATIC_LEGACY_TOOLS)
    register_schematic_tools(mcp, BridgeClient())
    return mcp
