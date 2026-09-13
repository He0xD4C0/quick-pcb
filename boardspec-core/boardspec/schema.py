"""JSON Schema loading for the BoardSpec DSL."""

from __future__ import annotations

import json
import os

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "schema",
    "board-spec-v0.1.schema.json",
)

_schema = None


def load_schema() -> dict:
    global _schema
    if _schema is None:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            _schema = json.load(f)
    return _schema
