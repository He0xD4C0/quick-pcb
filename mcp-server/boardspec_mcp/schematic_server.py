"""MCP registrations for single-page schematic tools."""

from __future__ import annotations

from functools import wraps
from inspect import signature
from typing import get_type_hints

from . import schematic_tools
from .protocol import (
    READ_ONLY,
    WRITE_ADD,
    WRITE_DESTRUCTIVE,
    WRITE_SET,
    SchematicResult,
    structured,
)
from .schematic_types import (
    ComponentPlacement,
    ComponentPlacementEdit,
    ComponentRemoval,
    NetFlagPlacement,
    NetLabelPlacement,
    NetMarkerAction,
    NetPortPlacement,
    NoConnectEdit,
    PlanOptions,
    SchematicPlan,
    SchematicRegion,
    SchematicWireAction,
    SchematicWireCreate,
    dump_model,
)


def register_schematic_tools(mcp, client) -> None:
    def register(annotations, *, raise_tool_error: bool = True):
        def decorate(function):
            original_signature = signature(function)
            hints = get_type_hints(function)

            @wraps(function)
            def wrapped(*args, **kwargs):
                return structured(
                    function(*args, **kwargs),
                    raise_tool_error=raise_tool_error,
                    result_type=SchematicResult,
                )

            wrapped.__annotations__ = {**hints, "return": SchematicResult}
            wrapped.__signature__ = original_signature.replace(
                parameters=[
                    parameter.replace(
                        annotation=hints.get(parameter.name, parameter.annotation)
                    )
                    for parameter in original_signature.parameters.values()
                ],
                return_annotation=SchematicResult,
            )
            return mcp.tool(
                annotations=annotations,
                structured_output=True,
            )(wrapped)

        return decorate

    @register(READ_ONLY)
    def get_eda_windows() -> dict:
        """List connected EasyEDA windows without switching the active window."""
        return schematic_tools.get_eda_windows(client)

    @register(READ_ONLY)
    def get_schematic_context(window_id: str | None = None) -> dict:
        """Read project, schematic, page and revision identity for one EDA window."""
        return schematic_tools.get_schematic_context(client, window_id)

    @register(WRITE_ADD)
    def create_project(window_id: str, friendly_name: str, project_name: str | None = None, description: str | None = None) -> dict:
        """Create a project only in a window that has no active document."""
        return schematic_tools.create_project(client, window_id, friendly_name, project_name, description)

    @register(WRITE_DESTRUCTIVE)
    def open_project(window_id: str, project_uuid: str, confirm_discard_unsaved: bool = False) -> dict:
        """Explicitly open a project; switching away requires explicit confirmation."""
        return schematic_tools.open_project(client, window_id, project_uuid, confirm_discard_unsaved)

    @register(WRITE_ADD)
    def create_schematic(window_id: str, name: str, confirm_discard_unsaved: bool = False) -> dict:
        """Create, open and name a schematic in the current project."""
        return schematic_tools.create_schematic(client, window_id, name, confirm_discard_unsaved)

    @register(WRITE_ADD)
    def create_schematic_page(window_id: str, schematic_uuid: str, name: str) -> dict:
        """Create and name a page without opening or saving it."""
        return schematic_tools.create_schematic_page(client, window_id, schematic_uuid, name)

    @register(WRITE_DESTRUCTIVE)
    def open_schematic_page(window_id: str, page_uuid: str, expected_context_revision: str, confirm_discard_unsaved: bool = False) -> dict:
        """Explicitly switch to a page after checking the source context."""
        return schematic_tools.open_schematic_page(client, window_id, page_uuid, expected_context_revision, confirm_discard_unsaved)

    @register(WRITE_DESTRUCTIVE)
    def save_schematic(window_id: str, expected_context_revision: str, expected_revision: str) -> dict:
        """Explicitly save the current schematic after revision checks."""
        return schematic_tools.save_schematic(client, window_id, expected_context_revision, expected_revision)

    @register(READ_ONLY)
    def get_schematic_summary(window_id: str | None = None, cursor: int | None = None, page_size: int = 100) -> dict:
        """Read compact single-page schematic counts, topology and strict DRC facts."""
        return schematic_tools.get_schematic_summary(client, window_id, cursor, page_size)

    @register(READ_ONLY)
    def get_schematic_components(window_id: str | None = None, designators: list[str] | None = None, region: SchematicRegion | None = None, include_pins: bool = False) -> dict:
        """Read exact schematic components and optionally their live pins."""
        return schematic_tools.get_schematic_components(client, window_id, designators, dump_model(region), include_pins)

    @register(READ_ONLY)
    def get_schematic_wiring(window_id: str | None = None, nets: list[str] | None = None, region: SchematicRegion | None = None) -> dict:
        """Read normalized wires, labels, ports and power flags."""
        return schematic_tools.get_schematic_wiring(client, window_id, nets, dump_model(region))

    @register(READ_ONLY)
    def get_schematic_violations(window_id: str | None = None, ids: list[str] | None = None, nets: list[str] | None = None, region: SchematicRegion | None = None) -> dict:
        """Run strict schematic DRC and return stable, filterable violations."""
        return schematic_tools.get_schematic_violations(client, window_id, ids, nets, dump_model(region))

    @register(READ_ONLY, raise_tool_error=False)
    def plan_schematic(spec_yaml: str, options: PlanOptions | None = None) -> dict:
        """Validate and expand BoardSpec, then build a deterministic logical plan."""
        return schematic_tools.plan_schematic(spec_yaml, dump_model(options))

    @register(READ_ONLY)
    def resolve_schematic_plan(plan: SchematicPlan, window_id: str, expected_context_revision: str, expected_revision: str) -> dict:
        """Resolve logical connections against live pin and bounding-box geometry."""
        return schematic_tools.resolve_schematic_plan(client, dump_model(plan), window_id, expected_context_revision, expected_revision)

    @register(READ_ONLY)
    def diff_schematic_plan(plan: SchematicPlan, window_id: str, expected_context_revision: str, expected_revision: str) -> dict:
        """Compare a plan with the current page without applying changes."""
        return schematic_tools.diff_schematic_plan(client, dump_model(plan), window_id, expected_context_revision, expected_revision)

    @register(READ_ONLY)
    def verify_schematic_topology(spec_yaml: str, window_id: str | None = None, base_dir: str | None = None) -> dict:
        """Compare expanded BoardSpec with the live Protel2 schematic netlist."""
        return schematic_tools.verify_schematic_topology(client, spec_yaml, window_id, base_dir)

    @register(READ_ONLY)
    def verify_schematic_readability(plan: SchematicPlan, window_id: str | None = None) -> dict:
        """Verify visible endpoint coverage and schematic marker collisions."""
        return schematic_tools.verify_schematic_readability(client, dump_model(plan), window_id)

    @register(WRITE_ADD)
    def place_schematic_components(window_id: str, expected_context_revision: str, expected_revision: str, placements: list[ComponentPlacement]) -> dict:
        """Place a checked batch of exact EasyEDA devices."""
        return schematic_tools.place_schematic_components(client, window_id, expected_context_revision, expected_revision, dump_model(placements))

    @register(WRITE_SET)
    def set_schematic_component_placement(window_id: str, expected_context_revision: str, expected_revision: str, edits: list[ComponentPlacementEdit]) -> dict:
        """Move, rotate or mirror existing components without changing identity."""
        return schematic_tools.set_schematic_component_placement(client, window_id, expected_context_revision, expected_revision, dump_model(edits))

    @register(WRITE_DESTRUCTIVE)
    def remove_schematic_components(window_id: str, expected_context_revision: str, expected_revision: str, removals: list[ComponentRemoval], confirm_topology_change: bool = False) -> dict:
        """Delete exact component primitive IDs with explicit topology confirmation."""
        return schematic_tools.remove_schematic_components(client, window_id, expected_context_revision, expected_revision, dump_model(removals), confirm_topology_change)

    @register(WRITE_ADD)
    def create_schematic_wires(window_id: str, expected_context_revision: str, expected_revision: str, wires: list[SchematicWireCreate]) -> dict:
        """Create orthogonal wires using exact pin selectors or grid points."""
        return schematic_tools.create_schematic_wires(client, window_id, expected_context_revision, expected_revision, dump_model(wires))

    @register(WRITE_DESTRUCTIVE)
    def edit_schematic_wires(window_id: str, expected_context_revision: str, expected_revision: str, actions: list[SchematicWireAction]) -> dict:
        """Modify or delete exact schematic wire primitive IDs."""
        return schematic_tools.edit_schematic_wires(client, window_id, expected_context_revision, expected_revision, dump_model(actions))

    @register(WRITE_ADD)
    def place_schematic_net_labels(window_id: str, expected_context_revision: str, expected_revision: str, placements: list[NetLabelPlacement]) -> dict:
        """Place local net labels at exact pins or coordinates."""
        return schematic_tools.place_schematic_net_labels(client, window_id, expected_context_revision, expected_revision, dump_model(placements))

    @register(WRITE_ADD)
    def place_schematic_net_ports(window_id: str, expected_context_revision: str, expected_revision: str, placements: list[NetPortPlacement]) -> dict:
        """Place explicit IN, OUT or BI page ports."""
        return schematic_tools.place_schematic_net_ports(client, window_id, expected_context_revision, expected_revision, dump_model(placements))

    @register(WRITE_ADD)
    def place_schematic_net_flags(window_id: str, expected_context_revision: str, expected_revision: str, placements: list[NetFlagPlacement]) -> dict:
        """Place explicit power or ground flags without name-based inference."""
        return schematic_tools.place_schematic_net_flags(client, window_id, expected_context_revision, expected_revision, dump_model(placements))

    @register(WRITE_DESTRUCTIVE)
    def edit_schematic_net_markers(window_id: str, expected_context_revision: str, expected_revision: str, actions: list[NetMarkerAction], confirm_topology_change: bool = False) -> dict:
        """Delete or replace exact net label, port or power-flag primitive IDs."""
        return schematic_tools.edit_schematic_net_markers(client, window_id, expected_context_revision, expected_revision, dump_model(actions), confirm_topology_change)

    @register(WRITE_SET)
    def set_schematic_no_connects(window_id: str, expected_context_revision: str, expected_revision: str, edits: list[NoConnectEdit]) -> dict:
        """Set exact No Connect pins under the checked-write protocol."""
        return schematic_tools.set_schematic_no_connects(client, window_id, expected_context_revision, expected_revision, dump_model(edits))
