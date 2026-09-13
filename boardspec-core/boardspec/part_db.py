"""Generic JSON part-database adapter and reference resolution.

A ``PartDB`` holds ``part_id -> record`` entries read from a JSON database in
the layout demonstrated by ``parts.demo.json``. A ``Resolver`` answers whether a
part reference is a project ``module``, a project ``physical`` definition, or a
``library`` part, and returns the matching pin list / footprint.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .diag import diag


def _dedupe(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


class PartDB:
    def __init__(self):
        self.parts = {}

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for pid, part in data.get("parts", {}).items():
            self.parts[pid] = dict(part)

    def get(self, ref: str):
        return self.parts.get(ref)

    def search(self, query: str, limit: Optional[int] = None):
        q = (query or "").lower()
        results = []
        for pid, part in self.parts.items():
            hay = (pid + " " + str(part.get("description", ""))).lower()
            if q in hay:
                results.append(self._summary(pid, part))
        if limit:
            results = results[:limit]
        return results

    def detail(self, ref: str):
        part = self.get(ref)
        if part is None:
            return None
        out = dict(part)
        out["part_id"] = ref
        out["power_pins"] = _dedupe(
            p.get("name") for p in part.get("pins", []) if p.get("type") == "power_in"
        )
        return out

    @staticmethod
    def _summary(pid, part):
        pins = part.get("pins", [])
        return {
            "part_id": pid,
            "description": part.get("description", ""),
            "pins": _dedupe(p.get("name") for p in pins),
            "power_pins": _dedupe(
                p.get("name") for p in pins if p.get("type") == "power_in"
            ),
            "footprint": part.get("footprint"),
            "source": part.get("source"),
            "complete": part.get("complete", True),
        }


class Resolver:
    def __init__(self, spec, part_db: PartDB):
        self.definitions = spec.get("definitions", {}) or {}
        self.part_db = part_db

    def resolve(self, ref):
        """Return ``(kind, data)`` where kind is module/physical/library/None."""
        if ref in self.definitions:
            d = self.definitions[ref]
            return ("module" if d.get("kind") == "module" else "physical"), d
        part = self.part_db.get(ref)
        if part is not None:
            return "library", part
        return None, None

    def pins(self, kind, data):
        if kind in ("physical", "library") and data:
            return data.get("pins", []) or []
        return []

    def footprint(self, kind, data):
        if kind in ("physical", "library") and data:
            return data.get("footprint")
        return None

    def reference_prefix(self, kind, data):
        if kind in ("physical", "library") and data:
            return data.get("reference_prefix")
        return None

    def source(self, kind, data):
        if kind in ("physical", "library") and data:
            source = data.get("source")
            return source if isinstance(source, dict) else {}
        return {}


def build_resolver(spec, base_dir: str, extra_dbs):
    """Load library part DBs from ``libraries[]`` and CLI ``--part-db`` flags.

    ``extra_dbs`` are absolute paths that override entries with the same part id
    loaded from ``libraries[].type: generic``.
    """
    part_db = PartDB()
    errors = []
    for lib in spec.get("libraries", []) or []:
        if lib.get("type") != "generic" or not lib.get("path"):
            continue
        path = lib["path"]
        if not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        try:
            part_db.load(path)
        except (OSError, ValueError) as exc:
            errors.append(
                diag(
                    "LIBRARY_LOAD_FAILED",
                    "/libraries",
                    f"failed to load library '{lib.get('id')}': {exc}",
                )
            )
    for path in extra_dbs:
        try:
            part_db.load(path)
        except (OSError, ValueError) as exc:
            errors.append(
                diag(
                    "LIBRARY_LOAD_FAILED",
                    "/libraries",
                    f"failed to load --part-db '{path}': {exc}",
                )
            )
    return Resolver(spec, part_db), errors


def split_part(ref: str):
    if ":" in ref:
        lib, _, part = ref.partition(":")
        return lib, part
    return "", ref
