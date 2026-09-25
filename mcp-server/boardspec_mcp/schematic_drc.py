"""Stable normalization for schematic DRC results."""

from __future__ import annotations

import hashlib
import json


def _walk(value, allow_strings: bool = True):
    if isinstance(value, list):
        child_strings = allow_strings and not any(
            isinstance(item, (dict, list)) for item in value
        )
        for child in value:
            yield from _walk(child, child_strings)
    elif isinstance(value, dict):
        described = value.get("message") or value.get("explanation") or value.get("objs")
        if (value.get("errorType") or value.get("name")) and described:
            yield value
            return
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                yield from _walk(
                    child, allow_strings=key not in {"objs", "explanation", "pos"}
                )
    elif isinstance(value, str) and allow_strings:
        yield {"errorType": "EDA DRC", "message": value}


def _message(row: dict):
    value = row.get("explanation")
    if isinstance(value, dict):
        return value.get("str") or value.get("message")
    return value if isinstance(value, str) else row.get("message")


def _position(row: dict) -> dict | None:
    pos = row.get("pos")
    if isinstance(pos, (list, tuple)):
        pos = {
            "x": pos[0] if len(pos) > 0 else None,
            "y": pos[1] if len(pos) > 1 else None,
        }
    if not isinstance(pos, dict):
        return None
    return {
        "x": pos.get("x") * 10 if pos.get("x") is not None else None,
        "y": pos.get("y") * 10 if pos.get("y") is not None else None,
    }


def flatten_schematic_drc(raw, page_uuid: str | None = None) -> list[dict]:
    result = {}
    for row in _walk(raw):
        signature = {
            "severity": row.get("severity") or row.get("level"),
            "type": row.get("errorType") or row.get("name"),
            "rule": row.get("ruleName"),
            "net": row.get("net"),
            "page": page_uuid,
            "objects": sorted(str(item) for item in (row.get("objs") or [])),
            "position": _position(row),
            "message": _message(row),
        }
        token = json.dumps(signature, ensure_ascii=False, sort_keys=True)
        violation_id = "sch-drc:" + hashlib.sha256(token.encode()).hexdigest()[:16]
        result[violation_id] = {
            "id": violation_id,
            **signature,
            "source_id": row.get("globalIndex"),
        }
    return [result[key] for key in sorted(result)]


def schematic_drc_delta(before: list[dict], after: list[dict]) -> dict:
    left = {row["id"]: row for row in before}
    right = {row["id"]: row for row in after}
    return {
        "before_count": len(left),
        "new": [right[key] for key in sorted(right.keys() - left)],
        "resolved": sorted(left.keys() - right),
        "remaining_count": len(right),
    }
