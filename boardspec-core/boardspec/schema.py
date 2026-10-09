"""JSON Schema loading for the BoardSpec DSL."""

from __future__ import annotations

import json
import os

from referencing import Registry, Resource

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema")
SCHEMA_PATHS = {
    "board-spec/v0.1": os.path.join(SCHEMA_DIR, "board-spec-v0.1.schema.json"),
    "board-spec/v0.2": os.path.join(SCHEMA_DIR, "board-spec-v0.2.schema.json"),
}

_schemas = {}


def load_schema(version: str = "board-spec/v0.1") -> dict:
    """Load one supported BoardSpec schema by its document version."""
    selected = version if version in SCHEMA_PATHS else "board-spec/v0.1"
    if selected not in _schemas:
        with open(SCHEMA_PATHS[selected], encoding="utf-8") as f:
            _schemas[selected] = json.load(f)
    return _schemas[selected]


def schema_registry() -> Registry:
    """Return a registry that resolves cross-version schema references."""
    registry = Registry()
    for version in SCHEMA_PATHS:
        schema = load_schema(version)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry
