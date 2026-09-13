"""BoardSpec MCP server entry point.

Exposes BoardSpec DSL tools (validate/expand/export) locally and EasyEDA Pro
tools (search_part/get_part/load_netlist/bridge_status) through the official
bridge. Tools that depend on the bridge return ``BRIDGE_UNAVAILABLE`` when it is
not reachable rather than fabricating part or pin data.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer

from .bridge_client import BridgeClient
from . import layout_tools, tools
from .layout_types import (
    KeepoutAction,
    OutlinePoint,
    PlacementEdit,
    PourAction,
    Region,
    RouteBranch,
    RouteRuleOverrides,
    RoutingAction,
    dump_model,
)

mcp = MCPServer(name="boardspec")

client = BridgeClient()


@mcp.tool()
def bridge_status() -> dict:
    """Check whether the EasyEDA bridge and EDA client are connected."""
    return tools.bridge_status(client)


@mcp.tool()
def search_part(query: str, limit: int = 10) -> dict:
    """Search the EasyEDA Pro device library for parts matching a keyword.

    Requires the EasyEDA bridge. Returns real device entries (uuid, libraryUuid,
    name, symbol, footprint) — never fabricated pins.
    """
    return tools.search_part(client, query, limit)


@mcp.tool()
def get_part(part_uuid: str, library_uuid: str = "") -> dict:
    """Fetch a device plus an embeddable, provenance-preserving physical definition."""
    return tools.get_part(client, part_uuid, library_uuid)


@mcp.tool()
def get_project_component(designator: str) -> dict:
    """Read one placed schematic component, including live pin types and NC flags."""
    return tools.get_project_component(client, designator)


@mcp.tool()
def get_netlist(
    netlist_type: str = "PROTEL2", document_kind: str = "schematic"
) -> dict:
    """Read the current schematic or PCB netlist in an exchange format."""
    return tools.get_netlist(client, netlist_type, document_kind)


@mcp.tool()
def set_no_connects(
    designator: str, pin_selectors: list[str], apply: bool = False
) -> dict:
    """Preview or set exact #PIN_NUMBER no-connect flags on a placed component."""
    return tools.set_no_connects(client, designator, pin_selectors, apply)


@mcp.tool()
def run_schematic_drc() -> dict:
    """Run strict schematic DRC and return detailed violations without opening UI."""
    return tools.run_schematic_drc(client)


@mcp.tool()
def run_pcb_drc() -> dict:
    """Run strict PCB DRC and return detailed violations without opening UI."""
    return tools.run_pcb_drc(client)


@mcp.tool()
def validate(spec_yaml: str) -> dict:
    """Validate a BoardSpec YAML document (schema + part/pin/ERC resolution).

    Returns ``{ok, errors, warnings}``. Errors carry code, path, message, hint.
    """
    return tools.validate(spec_yaml)


@mcp.tool()
def expand(spec_yaml: str) -> dict:
    """Recursively flatten ``kind: module`` definitions in a BoardSpec document."""
    return tools.expand(spec_yaml)


@mcp.tool()
def export(spec_yaml: str, target: str) -> dict:
    """Export a validated BoardSpec to netlist/BOM/diagram text.

    ``target`` is one of: protel2_netlist, kicad_netlist, bom_csv, mermaid.
    """
    return tools.export(spec_yaml, target)


@mcp.tool()
def load_netlist(
    netlist_text: str,
    netlist_type: str = "PROTEL2",
    document_kind: str = "pcb",
) -> dict:
    """Stage a netlist import for review in the active EasyEDA PCB.

    ``netlist_type`` is one of PROTEL2, JLCEDA, ALLEGRO, PADS.
    EasyEDA requires the user to review and apply the staged changes.
    """
    return tools.load_netlist(client, netlist_text, netlist_type, document_kind)


@mcp.tool()
def get_layout_summary(cursor: int | None = None, page_size: int = 100) -> dict:
    """Read a compact, columnar overview of the active PCB layout in mil."""
    return layout_tools.get_layout_summary(client, cursor, page_size)


@mcp.tool()
def get_layout_components(
    designators: list[str] | None = None,
    region: Region | None = None,
    include_pads: bool = False,
) -> dict:
    """Read exact component placement, optionally including live pad geometry."""
    return layout_tools.get_layout_components(
        client, designators, dump_model(region), include_pads
    )


@mcp.tool()
def get_layout_routing(
    nets: list[str] | None = None, region: Region | None = None
) -> dict:
    """Read exact trace, arc, via and polyline geometry by net or region."""
    return layout_tools.get_layout_routing(client, nets, dump_model(region))


@mcp.tool()
def get_board_geometry() -> dict:
    """Read board outline, layers, stack, keepouts, pours and opaque obstacles."""
    return layout_tools.get_board_geometry(client)


@mcp.tool()
def get_layout_rules() -> dict:
    """Read active PCB rules, net classes and differential-pair declarations."""
    return layout_tools.get_layout_rules(client)


@mcp.tool()
def get_layout_violations(
    ids: list[str] | None = None,
    nets: list[str] | None = None,
    region: Region | None = None,
) -> dict:
    """Run strict EasyEDA PCB DRC and return compact, filterable violations."""
    return layout_tools.get_layout_violations(client, ids, nets, dump_model(region))


@mcp.tool()
def set_component_placement(expected_revision: str, edits: list[PlacementEdit]) -> dict:
    """Directly place components by absolute coordinates or a relative anchor."""
    return layout_tools.set_component_placement(
        client, expected_revision, dump_model(edits)
    )


@mcp.tool()
def run_auto_layout(expected_revision: str) -> dict:
    """Run EasyEDA's whole-board auto-layout, then read back and run strict DRC."""
    return layout_tools.run_auto_layout(client, expected_revision)


@mcp.tool()
def create_route(
    expected_revision: str,
    net: str,
    branches: list[RouteBranch],
    rule_overrides: RouteRuleOverrides | None = None,
) -> dict:
    """Create exact routed branches from pad selectors and coordinate waypoints."""
    return layout_tools.create_route(
        client, expected_revision, net, dump_model(branches), dump_model(rule_overrides)
    )


@mcp.tool()
def edit_routing(expected_revision: str, actions: list[RoutingAction]) -> dict:
    """Modify or delete exact line, arc or via primitive IDs."""
    return layout_tools.edit_routing(client, expected_revision, dump_model(actions))


@mcp.tool()
def run_auto_routing(
    expected_revision: str,
    nets: list[str] | None = None,
    layers: list[int] | None = None,
    corner_style: Literal["45", "90"] = "45",
    existing_mode: Literal["keep", "remove"] = "keep",
    ignore_nets: list[str] | None = None,
) -> dict:
    """Run EasyEDA auto-routing for the requested nets and copper layers."""
    return layout_tools.run_auto_routing(
        client,
        expected_revision,
        nets,
        layers,
        corner_style,
        existing_mode,
        ignore_nets,
    )


@mcp.tool()
def set_board_outline(
    expected_revision: str,
    contours: list[list[OutlinePoint]],
    replace: bool = False,
) -> dict:
    """Create closed line contours on BoardOutline; replacement must be explicit."""
    return layout_tools.set_board_outline(
        client, expected_revision, dump_model(contours), replace
    )


@mcp.tool()
def edit_keepouts(expected_revision: str, actions: list[KeepoutAction]) -> dict:
    """Create, modify or delete EasyEDA PCB rule regions."""
    return layout_tools.edit_keepouts(client, expected_revision, dump_model(actions))


@mcp.tool()
def edit_copper_pours(
    expected_revision: str, actions: list[PourAction], rebuild: bool = True
) -> dict:
    """Create, modify or delete copper pours and optionally rebuild them."""
    return layout_tools.edit_copper_pours(
        client, expected_revision, dump_model(actions), rebuild
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
