"""Shared MCP metadata, annotations, and structured result helpers."""

from __future__ import annotations

from typing import Any, Literal, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

VERSION = "0.3.0"

ExportTarget = Literal["protel2_netlist", "kicad_netlist", "bom_csv", "mermaid"]
NetlistType = Literal["PROTEL2", "JLCEDA", "ALLEGRO", "PADS"]
DocumentKind = Literal["schematic", "pcb"]


class Diagnostic(BaseModel):
    """Stable BoardSpec or EDA diagnostic shape."""

    model_config = ConfigDict(extra="allow")

    code: str
    path: str | None = None
    message: str
    hint: str | None = None


class ToolResult(BaseModel):
    """Additive result envelope that preserves tool-specific top-level fields."""

    model_config = ConfigDict(extra="allow")

    ok: bool


class ContextIdentity(BaseModel):
    """Stable EasyEDA window, project, and document identity fields."""

    model_config = ConfigDict(extra="allow")

    project_uuid: str | None = None
    project_name: str | None = None
    schematic_uuid: str | None = None
    schematic_name: str | None = None
    page_uuid: str | None = None
    page_name: str | None = None
    document_uuid: str | None = None
    document_type: int | str | None = None
    tab_id: str | None = None
    window_id: str | None = None


class RevisionedResult(ToolResult):
    """Shared context and revision fields returned by checked EDA tools."""

    format: str | None = None
    source: ContextIdentity | str | None = None
    document: ContextIdentity | None = None
    context_revision: str | None = None
    revision: str | None = None
    revision_before: str | None = None
    revision_after: str | None = None


class ValidationResult(ToolResult):
    errors: list[Diagnostic] = Field(default_factory=list)
    warnings: list[Diagnostic] = Field(default_factory=list)


class ExpansionResult(ValidationResult):
    expanded_spec: dict[str, Any] | None = None


class ExportResult(ValidationResult):
    content: str | None = None


class BridgeStatusResult(ToolResult):
    code: str | None = None
    message: str | None = None
    service: str | None = None
    base_url: str | None = None
    eda_connected: bool | None = None
    eda_window_count: int | None = None
    active_window_id: str | None = None


class NetlistResult(ToolResult):
    result: str | None = None
    netlist_type: NetlistType | None = None
    document_kind: DocumentKind | None = None


class DRCResult(ToolResult):
    result: Any = None
    passed: bool | None = None


class StagedNetlistResult(ToolResult):
    result: Any = None
    staged: bool | None = None
    requires_user_confirmation: bool | None = None
    document_kind: DocumentKind | None = None
    message: str | None = None


class EDAResult(RevisionedResult):
    """Additive EDA result with common readback and diagnostic fields."""

    code: str | None = None
    message: str | None = None
    result: Any = None
    applied: bool | None = None
    partial: bool | None = None
    readback: dict[str, Any] | None = None
    topology: dict[str, Any] | None = None
    drc: dict[str, Any] | None = None
    counts: dict[str, Any] | None = None
    range: dict[str, Any] | None = None
    unit: str | None = None


class LayoutResult(EDAResult):
    """Layout read/write result with document and PCB revision identity."""


class SchematicResult(EDAResult):
    """Schematic read/write result with window, context, and page revisions."""


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE_ADD = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
WRITE_SET = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE_DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)

_TOOL_ERROR_CODES = {
    "BRIDGE_UNAVAILABLE",
    "BRIDGE_TIMEOUT",
    "BRIDGE_HTTP_ERROR",
    "BRIDGE_BAD_RESPONSE",
    "EDA_UNAVAILABLE",
    "EDA_WINDOW_UNAVAILABLE",
    "EDA_WRITE_REJECTED",
    "COMPONENT_NOT_FOUND",
    "CONTEXT_CHANGED",
    "STALE_REVISION",
    "STALE_SCHEMATIC",
    "CONTEXT_MISMATCH",
    "CONTEXT_REVISION_MISMATCH",
    "REVISION_MISMATCH",
    "WRITE_STATUS_UNKNOWN",
    "WRITE_VERIFICATION_FAILED",
    "DOCUMENT_SWITCH_UNSAFE",
    "DRC_BASELINE_FAILED",
    "SAVE_FAILED",
    "SCHEMATIC_CONTEXT_UNAVAILABLE",
    "AMBIGUOUS_COMPONENT",
    "INVALID_CORNER_STYLE",
    "INVALID_EDIT",
    "INVALID_LAYER",
    "INVALID_NETLIST",
    "INVALID_OUTLINE",
    "INVALID_ROUTE",
    "INVALID_ROUTE_POINT",
    "NET_NOT_FOUND",
}


ResultT = TypeVar("ResultT", bound=ToolResult)


def structured(
    payload: dict[str, Any],
    *,
    raise_tool_error: bool = False,
    result_type: type[ResultT] = ToolResult,
) -> ResultT:
    """Validate a result and surface anticipated transport/state failures."""
    if raise_tool_error and not payload.get("ok", False):
        code = str(payload.get("code") or "")
        if code in _TOOL_ERROR_CODES:
            message = str(payload.get("message") or code)
            raise ToolError(f"{code}: {message}")
    return result_type.model_validate(payload)


_SERVER_DETAILS = {
    "all": {
        "name": "boardspec",
        "title": "Quick PCB BoardSpec",
        "description": "BoardSpec plus checked EasyEDA Pro layout and schematic tools.",
        "instructions": (
            "Use BoardSpec for coordinate-free connectivity. Validate before expand or export. "
            "Before any EasyEDA write, read the current window, document, and revision. Treat "
            "netlist import as staged until the user applies it in EasyEDA. Never claim save, "
            "routing, DRC, or production readiness without readback evidence."
        ),
    },
    "core": {
        "name": "boardspec-core",
        "title": "Quick PCB BoardSpec Core",
        "description": "Validate, expand, and export coordinate-free BoardSpec documents.",
        "instructions": (
            "BoardSpec declares components, nets, and constraints without drawing coordinates. "
            "Validate before expand or export. Resolve relative libraries from base_dir when it "
            "is supplied, and never invent part, pin, or footprint data."
        ),
    },
    "layout": {
        "name": "boardspec-layout",
        "title": "Quick PCB EasyEDA Layout",
        "description": "Read and make revision-checked changes to EasyEDA Pro PCB layouts.",
        "instructions": (
            "Confirm bridge identity and edaConnected before use. Read the current PCB and "
            "revision before every write. Netlist import is staged for EasyEDA review and is not "
            "applied or saved by this tool. Read back changes and run strict PCB DRC."
        ),
    },
    "schematic": {
        "name": "boardspec-schematic",
        "title": "Quick PCB EasyEDA Schematic",
        "description": "Plan, draw, and verify revision-checked EasyEDA Pro schematics.",
        "instructions": (
            "Use explicit window, context, and revision identity. Follow plan, resolve, diff, "
            "write, readback, topology, readability, and DRC. Never switch, overwrite, delete, "
            "or save without explicit user intent and the required confirmation arguments."
        ),
    },
}


def make_server(profile: Literal["all", "core", "layout", "schematic"]) -> MCPServer:
    return MCPServer(version=VERSION, **_SERVER_DETAILS[profile])
