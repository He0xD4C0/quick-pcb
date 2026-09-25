"""BoardSpec MCP server entry point.

Exposes BoardSpec DSL tools (validate/expand/export) locally and EasyEDA Pro
tools (search_part/get_part/load_netlist/bridge_status) through the official
bridge. Tools that depend on the bridge return ``BRIDGE_UNAVAILABLE`` when it is
not reachable rather than fabricating part or pin data.
"""

from __future__ import annotations

from typing import Literal

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
from .protocol import (
    DocumentKind,
    BridgeStatusResult,
    DRCResult,
    EDAResult,
    ExpansionResult,
    ExportResult,
    ExportTarget,
    LayoutResult,
    NetlistResult,
    NetlistType,
    READ_ONLY,
    WRITE_ADD,
    WRITE_DESTRUCTIVE,
    WRITE_SET,
    StagedNetlistResult,
    ValidationResult,
    make_server,
    structured,
)
from .schematic_server import register_schematic_tools

mcp = make_server("all")

client = BridgeClient()
register_schematic_tools(mcp, client)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def bridge_status() -> BridgeStatusResult:
    """Check whether the EasyEDA bridge and EDA client are connected."""
    return structured(tools.bridge_status(client), result_type=BridgeStatusResult)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def search_part(query: str, limit: int = 10) -> EDAResult:
    """Search the EasyEDA Pro device library for parts matching a keyword.

    Requires the EasyEDA bridge. Returns real device entries (uuid, libraryUuid,
    name, symbol, footprint) — never fabricated pins.
    """
    return structured(tools.search_part(client, query, limit), raise_tool_error=True, result_type=EDAResult)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_part(part_uuid: str, library_uuid: str = "") -> EDAResult:
    """Fetch a device plus an embeddable, provenance-preserving physical definition."""
    return structured(tools.get_part(client, part_uuid, library_uuid), raise_tool_error=True, result_type=EDAResult)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_project_component(designator: str) -> EDAResult:
    """Read one placed schematic component, including live pin types and NC flags."""
    return structured(
        tools.get_project_component(client, designator), raise_tool_error=True, result_type=EDAResult
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_netlist(
    netlist_type: NetlistType = "PROTEL2",
    document_kind: DocumentKind = "schematic",
) -> NetlistResult:
    """Read the current schematic or PCB netlist in an exchange format."""
    return structured(
        tools.get_netlist(client, netlist_type, document_kind), raise_tool_error=True, result_type=NetlistResult
    )


@mcp.tool(annotations=WRITE_DESTRUCTIVE, structured_output=True)
def set_no_connects(
    designator: str, pin_selectors: list[str], apply: bool = False
) -> EDAResult:
    """Preview or set exact #PIN_NUMBER no-connect flags on a placed component."""
    return structured(
        tools.set_no_connects(client, designator, pin_selectors, apply),
        raise_tool_error=True, result_type=EDAResult,
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def run_schematic_drc() -> DRCResult:
    """Run strict schematic DRC and return detailed violations without opening UI."""
    return structured(tools.run_schematic_drc(client), raise_tool_error=True, result_type=DRCResult)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def run_pcb_drc() -> DRCResult:
    """Run strict PCB DRC and return detailed violations without opening UI."""
    return structured(tools.run_pcb_drc(client), raise_tool_error=True, result_type=DRCResult)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def validate(spec_yaml: str, base_dir: str | None = None) -> ValidationResult:
    """Validate a BoardSpec YAML document (schema + part/pin/ERC resolution).

    Returns ``{ok, errors, warnings}``. Errors carry code, path, message, hint.
    """
    return structured(tools.validate(spec_yaml, base_dir), result_type=ValidationResult)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def expand(spec_yaml: str, base_dir: str | None = None) -> ExpansionResult:
    """Recursively flatten ``kind: module`` definitions in a BoardSpec document."""
    return structured(tools.expand(spec_yaml, base_dir), result_type=ExpansionResult)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def export(
    spec_yaml: str, target: ExportTarget, base_dir: str | None = None
) -> ExportResult:
    """Export a validated BoardSpec to netlist/BOM/diagram text.

    ``target`` is one of: protel2_netlist, kicad_netlist, bom_csv, mermaid.
    """
    return structured(tools.export(spec_yaml, target, base_dir), result_type=ExportResult)


@mcp.tool(annotations=WRITE_DESTRUCTIVE, structured_output=True)
def load_netlist(
    netlist_text: str,
    netlist_type: NetlistType = "PROTEL2",
    document_kind: DocumentKind = "pcb",
) -> StagedNetlistResult:
    """Stage a netlist import for review in the active EasyEDA PCB.

    ``netlist_type`` is one of PROTEL2, JLCEDA, ALLEGRO, PADS.
    EasyEDA requires the user to review and apply the staged changes.
    """
    return structured(
        tools.load_netlist(client, netlist_text, netlist_type, document_kind),
        raise_tool_error=True, result_type=StagedNetlistResult,
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_layout_summary(
    cursor: int | None = None, page_size: int = 100
) -> LayoutResult:
    """Read a compact, columnar overview of the active PCB layout in mil."""
    return structured(
        layout_tools.get_layout_summary(client, cursor, page_size),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_layout_components(
    designators: list[str] | None = None,
    region: Region | None = None,
    include_pads: bool = False,
) -> LayoutResult:
    """Read exact component placement, optionally including live pad geometry."""
    return structured(
        layout_tools.get_layout_components(
            client, designators, dump_model(region), include_pads
        ),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_layout_routing(
    nets: list[str] | None = None, region: Region | None = None
) -> LayoutResult:
    """Read exact trace, arc, via and polyline geometry by net or region."""
    return structured(
        layout_tools.get_layout_routing(client, nets, dump_model(region)),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_board_geometry() -> LayoutResult:
    """Read board outline, layers, stack, keepouts, pours and opaque obstacles."""
    return structured(
        layout_tools.get_board_geometry(client),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_layout_rules() -> LayoutResult:
    """Read active PCB rules, net classes and differential-pair declarations."""
    return structured(
        layout_tools.get_layout_rules(client),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_layout_violations(
    ids: list[str] | None = None,
    nets: list[str] | None = None,
    region: Region | None = None,
) -> LayoutResult:
    """Run strict EasyEDA PCB DRC and return compact, filterable violations."""
    return structured(
        layout_tools.get_layout_violations(client, ids, nets, dump_model(region)),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=WRITE_SET, structured_output=True)
def set_component_placement(
    expected_revision: str, edits: list[PlacementEdit]
) -> LayoutResult:
    """Directly place components by absolute coordinates or a relative anchor."""
    return structured(
        layout_tools.set_component_placement(
            client, expected_revision, dump_model(edits)
        ),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=WRITE_DESTRUCTIVE, structured_output=True)
def run_auto_layout(expected_revision: str) -> LayoutResult:
    """Run EasyEDA's whole-board auto-layout, then read back and run strict DRC."""
    return structured(
        layout_tools.run_auto_layout(client, expected_revision),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=WRITE_ADD, structured_output=True)
def create_route(
    expected_revision: str,
    net: str,
    branches: list[RouteBranch],
    rule_overrides: RouteRuleOverrides | None = None,
) -> LayoutResult:
    """Create exact routed branches from pad selectors and coordinate waypoints."""
    return structured(
        layout_tools.create_route(
            client,
            expected_revision,
            net,
            dump_model(branches),
            dump_model(rule_overrides),
        ),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=WRITE_DESTRUCTIVE, structured_output=True)
def edit_routing(
    expected_revision: str, actions: list[RoutingAction]
) -> LayoutResult:
    """Modify or delete exact line, arc or via primitive IDs."""
    return structured(
        layout_tools.edit_routing(client, expected_revision, dump_model(actions)),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=WRITE_DESTRUCTIVE, structured_output=True)
def run_auto_routing(
    expected_revision: str,
    nets: list[str] | None = None,
    layers: list[int] | None = None,
    corner_style: Literal["45", "90"] = "45",
    existing_mode: Literal["keep", "remove"] = "keep",
    ignore_nets: list[str] | None = None,
) -> LayoutResult:
    """Run EasyEDA auto-routing for the requested nets and copper layers."""
    return structured(
        layout_tools.run_auto_routing(
            client,
            expected_revision,
            nets,
            layers,
            corner_style,
            existing_mode,
            ignore_nets,
        ),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=WRITE_DESTRUCTIVE, structured_output=True)
def set_board_outline(
    expected_revision: str,
    contours: list[list[OutlinePoint]],
    replace: bool = False,
) -> LayoutResult:
    """Create closed line contours on BoardOutline; replacement must be explicit."""
    return structured(
        layout_tools.set_board_outline(
            client, expected_revision, dump_model(contours), replace
        ),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=WRITE_DESTRUCTIVE, structured_output=True)
def edit_keepouts(
    expected_revision: str, actions: list[KeepoutAction]
) -> LayoutResult:
    """Create, modify or delete EasyEDA PCB rule regions."""
    return structured(
        layout_tools.edit_keepouts(client, expected_revision, dump_model(actions)),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


@mcp.tool(annotations=WRITE_DESTRUCTIVE, structured_output=True)
def edit_copper_pours(
    expected_revision: str, actions: list[PourAction], rebuild: bool = True
) -> LayoutResult:
    """Create, modify or delete copper pours and optionally rebuild them."""
    return structured(
        layout_tools.edit_copper_pours(
            client, expected_revision, dump_model(actions), rebuild
        ),
        raise_tool_error=True,
        result_type=LayoutResult,
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
