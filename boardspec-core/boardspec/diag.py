"""Structured diagnostic helpers."""

from __future__ import annotations

from typing import Optional


def diag(code: str, path: str, message: str, hint: Optional[str] = None) -> dict:
    """Build a structured diagnostic object.

    ``code`` is a stable machine-readable code; ``path`` is a JSON Pointer into
    the spec; ``message`` is human-readable; ``hint`` is an optional actionable
    suggestion.
    """
    d = {"code": code, "path": path, "message": message}
    if hint:
        d["hint"] = hint
    return d
