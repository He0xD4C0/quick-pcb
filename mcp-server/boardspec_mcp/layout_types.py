"""Explicit MCP input schemas for EasyEDA PCB layout tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Region(StrictModel):
    left: float
    right: float
    top: float
    bottom: float


class Point(StrictModel):
    x: float
    y: float


class OutlinePoint(Point):
    width: float | None = None


class PlacementEdit(StrictModel):
    designator: str
    x: float | None = None
    y: float | None = None
    at: Point | None = None
    relative_to: str | None = Field(
        default=None,
        description="Component designator or exact DESIGNATOR.#PAD selector",
    )
    dx: float = 0
    dy: float = 0
    layer: Literal[1, 2] | None = None
    rotation: float | None = None
    locked: bool | None = None


class RoutePoint(Point):
    layer: int | None = None


class RouteBranch(StrictModel):
    start: str | RoutePoint
    end: str | RoutePoint
    waypoints: list[str | RoutePoint] = Field(default_factory=list)


class RouteRuleOverrides(StrictModel):
    layer: int = 1
    width: float | None = None
    hole_diameter: float | None = None
    diameter: float | None = None
    via_type: Literal[0, 1, 2] = 0
    blind_via_rule: str | None = None


class RoutingProperties(StrictModel):
    net: str | None = None
    layer: int | None = None
    start_x: float | None = None
    start_y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    angle: float | None = None
    width: float | None = None
    x: float | None = None
    y: float | None = None
    hole_diameter: float | None = None
    diameter: float | None = None
    via_type: Literal[0, 1, 2] | None = None
    blind_via_rule: str | None = None
    locked: bool | None = None


class RoutingAction(StrictModel):
    op: Literal["modify", "delete"]
    type: Literal["line", "arc", "via"]
    id: str
    properties: RoutingProperties | None = None


PolygonSource = list[str | float | int]


class KeepoutAction(StrictModel):
    op: Literal["create", "modify", "delete"]
    id: str | None = None
    polygon: PolygonSource | None = None
    layer: int | None = None
    rule_types: list[Literal[2, 5, 6, 7, 8, 9]] | None = None
    name: str | None = None
    width: float | None = None
    locked: bool | None = None


class PourAction(StrictModel):
    op: Literal["create", "modify", "delete"]
    id: str | None = None
    polygon: PolygonSource | None = None
    net: str | None = None
    layer: int | None = None
    fill_method: Literal["45grid", "90grid", "solid"] | None = None
    preserve_islands: bool | None = None
    name: str | None = None
    priority: int | None = None
    width: float | None = None
    locked: bool | None = None


def dump_model(value):
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    if isinstance(value, list):
        return [dump_model(item) for item in value]
    return value
