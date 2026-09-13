"""Normalize EasyEDA's nested PCB DRC response and compare two checks."""

from __future__ import annotations

import hashlib
import json


def _walk(value, allow_strings: bool = True):
    if isinstance(value, list):
        for item in value:
            yield from _walk(item, allow_strings)
    elif isinstance(value, dict):
        identified = value.get("errorType") or value.get("globalIndex")
        described = (
            value.get("objs")
            or value.get("explanation")
            or value.get("message")
            or value.get("pos")
        )
        if (identified or value.get("name")) and described:
            yield value
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                yield from _walk(
                    child, allow_strings=key not in {"objs", "explanation", "pos"}
                )
    elif isinstance(value, str) and allow_strings:
        yield {"errorType": "EDA DRC", "message": value}


def _message(item: dict) -> str | None:
    explanation = item.get("explanation")
    if isinstance(explanation, dict):
        return explanation.get("str") or explanation.get("message")
    if isinstance(explanation, str):
        return explanation
    return item.get("message")


def _position(item: dict) -> dict | None:
    pos = item.get("pos")
    if isinstance(pos, (list, tuple)):
        return {
            "x": pos[0] if len(pos) > 0 else None,
            "y": pos[1] if len(pos) > 1 else None,
        }
    return pos if isinstance(pos, dict) else None


def _signature(item: dict) -> str:
    pos = _position(item) or {}
    signature = {
        "type": item.get("errorType") or item.get("name"),
        "rule": item.get("ruleName"),
        "net": item.get("net"),
        "objects": sorted(str(obj) for obj in (item.get("objs") or [])),
        "position": [pos.get("x"), pos.get("y")],
    }
    payload = json.dumps(signature, sort_keys=True, separators=(",", ":"))
    return "drc:" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def flatten_drc(raw) -> list[dict]:
    seen: set[str] = set()
    result = []
    for item in _walk(raw):
        violation_id = _signature(item)
        if violation_id in seen:
            continue
        seen.add(violation_id)
        result.append(
            {
                "id": violation_id,
                "type": item.get("errorType") or item.get("name"),
                "object_type": item.get("errorObjType"),
                "rule": item.get("ruleName"),
                "net": item.get("net"),
                "objects": item.get("objs") or [],
                "position": _position(item),
                "message": _message(item),
                "source_id": item.get("globalIndex"),
            }
        )
    return sorted(result, key=lambda row: row["id"])


def drc_delta(before, after) -> dict:
    before_rows = (
        before
        if all(isinstance(row, dict) and "id" in row for row in before)
        else flatten_drc(before)
    )
    after_rows = (
        after
        if all(isinstance(row, dict) and "id" in row for row in after)
        else flatten_drc(after)
    )
    before_by_id = {row["id"]: row for row in before_rows}
    after_by_id = {row["id"]: row for row in after_rows}
    return {
        "before_count": len(before_rows),
        "new": [after_by_id[key] for key in sorted(after_by_id.keys() - before_by_id)],
        "resolved": sorted(before_by_id.keys() - after_by_id),
        "remaining_count": len(after_rows),
    }
