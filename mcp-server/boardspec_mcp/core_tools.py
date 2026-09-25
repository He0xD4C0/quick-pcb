"""Coordinate-free BoardSpec MCP operations."""

from __future__ import annotations

import os

import boardspec
from boardspec.exporters import (
    render_bom_csv,
    render_kicad_netlist,
    render_mermaid,
    render_protel2_netlist,
)
from boardspec.yaml_io import YAMLError, format_yaml_error, load_yaml_text

EXPORTERS = {
    "kicad_netlist": render_kicad_netlist,
    "protel2_netlist": render_protel2_netlist,
    "bom_csv": render_bom_csv,
    "mermaid": render_mermaid,
}


def _load_spec(yaml_text: str):
    spec = load_yaml_text(yaml_text)
    return spec if isinstance(spec, dict) else None


def _analyze(yaml_text: str, base_dir: str | None = None):
    """Validate and expand YAML, resolving libraries from an explicit base."""
    try:
        spec = _load_spec(yaml_text)
    except YAMLError as exc:
        return None, [{
            "code": "SCHEMA_INVALID",
            "path": "/",
            "message": format_yaml_error(exc),
            "hint": "Fix the YAML syntax and retry validation.",
        }], []
    if spec is None:
        return None, [{"code": "SCHEMA_INVALID", "path": "/", "message": "not a mapping"}], []
    resolver_base = os.path.abspath(base_dir) if base_dir else os.getcwd()
    resolver, lib_errors = boardspec.build_resolver(spec, resolver_base, [])
    expanded, errors, warnings = boardspec.analyze(spec, resolver)
    return expanded, lib_errors + errors, warnings


def validate(yaml_text: str, base_dir: str | None = None) -> dict:
    _, errors, warnings = _analyze(yaml_text, base_dir)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def expand(yaml_text: str, base_dir: str | None = None) -> dict:
    expanded, errors, warnings = _analyze(yaml_text, base_dir)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "expanded_spec": None}
    return {"ok": True, "errors": errors, "warnings": warnings, "expanded_spec": expanded}


def export(yaml_text: str, target: str, base_dir: str | None = None) -> dict:
    if target not in EXPORTERS:
        return {
            "ok": False,
            "errors": [{
                "code": "UNKNOWN_TARGET",
                "path": "/outputs",
                "message": f"unknown export target '{target}'",
                "hint": "available: " + ", ".join(sorted(EXPORTERS)),
            }],
            "warnings": [],
        }
    expanded, errors, warnings = _analyze(yaml_text, base_dir)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    spec = _load_spec(yaml_text)
    resolver_base = os.path.abspath(base_dir) if base_dir else os.getcwd()
    resolver, lib_errors = boardspec.build_resolver(spec, resolver_base, [])
    if lib_errors:
        return {"ok": False, "errors": lib_errors, "warnings": warnings}
    return {
        "ok": True,
        "errors": errors,
        "warnings": warnings,
        "content": EXPORTERS[target](expanded, resolver),
    }
