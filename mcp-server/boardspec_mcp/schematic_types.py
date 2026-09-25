"""Strict public input models for the single-page Schematic MCP."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SchematicPoint(StrictModel):
    x: float
    y: float


class SchematicRegion(StrictModel):
    left: float
    right: float
    top: float
    bottom: float


class MeasuredGeometry(StrictModel):
    width: float | None = None
    height: float | None = None
    min_dx: float | None = None
    max_dx: float | None = None
    min_dy: float | None = None
    max_dy: float | None = None


class PlanOptions(StrictModel):
    page_policy: Literal["single_page"] = "single_page"
    wiring_policy: Literal["hybrid"] = "hybrid"
    grid_mil: int = Field(default=100, ge=10)
    column_gap_mil: int = Field(default=1000, ge=100)
    row_gap_mil: int = Field(default=600, ge=100)
    group_by_module: bool = True
    high_fanout_primitive: Literal["auto", "label", "port"] = "auto"
    readability_policy: Literal["standard_hybrid"] = "standard_hybrid"
    stub_lengths_mil: list[int] = Field(
        default_factory=lambda: [200, 300, 400, 500, 600]
    )
    marker_clearance_mil: int = Field(default=100, ge=0)
    cross_region_distance_mil: int = Field(default=2000, ge=100)
    use_trusted_pin_directions: bool = True
    preserve_existing_placements: bool = False
    measured_geometry: dict[str, MeasuredGeometry] = Field(default_factory=dict)
    base_dir: str | None = Field(
        default=None,
        description="Directory used to resolve relative BoardSpec library paths",
    )

    @model_validator(mode="after")
    def validate_readability_grid(self):
        if not self.stub_lengths_mil:
            raise ValueError("stub_lengths_mil cannot be empty")
        if len(self.stub_lengths_mil) != len(set(self.stub_lengths_mil)):
            raise ValueError("stub_lengths_mil must be unique")
        if any(value <= 0 or value % 10 for value in self.stub_lengths_mil):
            raise ValueError("stub lengths must be positive 10 mil grid values")
        if self.marker_clearance_mil % 10:
            raise ValueError("marker clearance must use the 10 mil grid")
        if self.cross_region_distance_mil % 10:
            raise ValueError("cross-region distance must use the 10 mil grid")
        return self


class ComponentPlacement(StrictModel):
    client_id: str
    library_uuid: str
    device_uuid: str
    device_name: str | None = None
    designator: str
    x: float
    y: float
    rotation: float = 0
    mirror: bool = False
    sub_part_name: str | None = None


class ComponentPlacementEdit(StrictModel):
    designator: str
    x: float | None = None
    y: float | None = None
    rotation: float | None = None
    mirror: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(
            value is None
            for value in (self.x, self.y, self.rotation, self.mirror)
        ):
            raise ValueError("at least one placement property is required")
        return self


class ComponentRemoval(StrictModel):
    id: str


Endpoint = str | SchematicPoint


class SchematicWireBranch(StrictModel):
    client_id: str
    start: Endpoint
    end: Endpoint
    waypoints: list[SchematicPoint] = Field(default_factory=list)
    role: Literal["direct", "stub"] | None = None
    anchor: str | None = None


class SchematicWireCreate(StrictModel):
    net: str
    branches: list[SchematicWireBranch]


class SchematicWireProperties(StrictModel):
    net: str | None = None
    points: list[SchematicPoint] | None = None


class SchematicWireAction(StrictModel):
    op: Literal["modify", "delete"]
    id: str
    properties: SchematicWireProperties | None = None


class AnchoredMarker(StrictModel):
    client_id: str
    net: str
    at: str | SchematicPoint
    rotation: float = 0
    mirror: bool = False
    anchor: str | None = None
    side: Literal["left", "right", "top", "bottom"] | None = None


class NetLabelPlacement(AnchoredMarker):
    pass


class NetPortPlacement(AnchoredMarker):
    direction: Literal["IN", "OUT", "BI"]


class NetFlagPlacement(AnchoredMarker):
    identification: Literal["Power", "Ground", "AnalogGround", "ProtectGround"]


class NoConnectEdit(StrictModel):
    designator: str
    pin_selectors: list[str]


class SchematicConnectionEndpoint(StrictModel):
    selector: str
    region: str
    pin_type: str | None = None
    pin_type_trusted: bool = False


class SchematicConnectionIntent(StrictModel):
    net: str
    kind: str | None = None
    strategy: Literal["direct", "label", "port", "flag"]
    endpoints: list[SchematicConnectionEndpoint]


class SchematicVisualSummary(StrictModel):
    expected_endpoints: int
    resolved_endpoints: int
    marker_endpoints: int
    direct_endpoints: int
    fallbacks: list[dict] = Field(default_factory=list)


class NetMarkerSpec(StrictModel):
    kind: Literal["label", "port", "flag"]
    client_id: str
    net: str
    at: SchematicPoint
    rotation: float = 0
    mirror: bool = False
    anchor: str | None = None
    side: Literal["left", "right", "top", "bottom"] | None = None
    direction: Literal["IN", "OUT", "BI"] | None = None
    identification: Literal["Power", "Ground", "AnalogGround", "ProtectGround"] | None = None

    @model_validator(mode="after")
    def require_kind_properties(self):
        if self.kind == "port" and self.direction is None:
            raise ValueError("port replacement requires direction")
        if self.kind == "flag" and self.identification is None:
            raise ValueError("flag replacement requires identification")
        if self.kind == "label" and (self.direction or self.identification):
            raise ValueError("label replacement cannot have port or flag properties")
        return self


class NetMarkerAction(StrictModel):
    op: Literal["delete", "replace"]
    kind: Literal["label", "port", "flag"]
    id: str
    replacement: NetMarkerSpec | None = None

    @model_validator(mode="after")
    def require_replacement(self):
        if self.op == "replace" and self.replacement is None:
            raise ValueError("replace action requires replacement")
        if self.op == "delete" and self.replacement is not None:
            raise ValueError("delete action cannot include replacement")
        if self.replacement and self.replacement.kind != self.kind:
            raise ValueError("replacement kind must match action kind")
        return self


class PlannedComponent(ComponentPlacement):
    logical_path: str


class SchematicTopology(StrictModel):
    components: list[str]
    nets: dict[str, list[tuple[str, str]]]


class SchematicPlan(StrictModel):
    format: Literal["schematic-plan/v0.1", "schematic-plan/v0.2"]
    phase: Literal["logical", "resolved"] | None = None
    options: PlanOptions
    placements: list[PlannedComponent]
    wires: list[SchematicWireCreate]
    labels: list[NetLabelPlacement]
    ports: list[NetPortPlacement]
    flags: list[NetFlagPlacement]
    no_connects: list[NoConnectEdit]
    connection_intents: list[SchematicConnectionIntent] = Field(default_factory=list)
    visual: SchematicVisualSummary | None = None
    topology: SchematicTopology
    topology_hash: str
    plan_hash: str


def dump_model(value):
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    if isinstance(value, list):
        return [dump_model(item) for item in value]
    return value
