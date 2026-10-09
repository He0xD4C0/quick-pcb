"""Public behavior for the single-page EasyEDA Schematic MCP."""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from .bridge_client import BridgeClient
from .schematic_bridge import (
    _execute,
    capture_schematic,
    capture_window_context,
    create_page_program,
    create_project_program,
    create_schematic_program,
    guarded_program,
    open_page_program,
    open_project_program,
    page_format_fields,
    page_format_program,
    page_format_structure,
    run_strict_drc,
    save_program,
)
from .schematic_codec import (
    columnar,
    context_revision,
    natural_key,
    normalize_state,
    paginate,
    primitive_in_region,
    schematic_revision,
)
from .schematic_drc import flatten_schematic_drc, schematic_drc_delta
from .schematic_plan import (
    build_plan,
    compare_topology,
    diff_plan,
    expected_generated_nets,
    expected_netlist,
)
from .schematic_readability import resolve_plan, verify_readability

def _error(code: str, message: str, **extra) -> dict:
    return {"ok": False, "code": code, "message": message, **extra}


def _write_status_unknown(response: dict) -> bool:
    return response.get("code") == "BRIDGE_TIMEOUT" or int(response.get("status_code") or 0) >= 500

def _window(client: BridgeClient, window_id: str | None):
    if window_id:
        listing = client.list_windows()
        if not listing.get("ok"):
            return None, listing
        connected = [
            item for item in listing.get("windows", [])
            if item.get("id") == window_id and item.get("connected", True)
        ]
        if not connected:
            return None, _error(
                "EDA_WINDOW_UNAVAILABLE",
                "target EDA window is no longer connected",
                window_id=window_id,
            )
        return window_id, None
    health = client.health()
    if not health.get("ok"):
        return None, health
    active = health.get("active_window_id")
    if not active:
        return None, _error("SCHEMATIC_CONTEXT_UNAVAILABLE", "bridge has no active EDA window")
    return active, None


def _state(client: BridgeClient, window_id: str | None):
    target, error = _window(client, window_id)
    if error:
        return None, None, error
    response = capture_schematic(client, target)
    if not response.get("ok"):
        return None, target, response
    return normalize_state(response["result"], target), target, None


def _raw_context(client: BridgeClient, window_id: str | None):
    target, error = _window(client, window_id)
    if error:
        return None, None, error
    response = capture_window_context(client, target)
    if not response.get("ok"):
        return None, target, response
    return response["result"], target, None


def _active_document(source: dict) -> bool:
    document_type = source.get("document_type")
    return (
        str(source.get("document_uuid") or "0") not in {"", "0", "None"}
        and document_type not in {None, -1, "-1", 0, "0"}
    )


def _drc(client: BridgeClient, target: str, page_uuid: str | None):
    response = run_strict_drc(client, target)
    if not response.get("ok"):
        return None, response
    return flatten_schematic_drc(response.get("result"), page_uuid), None


def get_eda_windows(client: BridgeClient) -> dict:
    response = client.list_windows()
    if response.get("ok"):
        response["window_count"] = len(response.get("windows") or [])
    return response


def get_schematic_context(client: BridgeClient, window_id: str | None = None) -> dict:
    source, _, error = _raw_context(client, window_id)
    if error:
        return error
    return {
        "ok": True,
        "format": "schematic/easyeda-v0.1",
        "source": source,
        "context_revision": context_revision(source),
        "has_active_document": _active_document(source),
        "has_active_schematic": bool(source.get("page_uuid")),
    }


def create_project(client, window_id, friendly_name, project_name=None, description=None):
    source, target, error = _raw_context(client, window_id)
    if error:
        return error
    if _active_document(source):
        return _error("DOCUMENT_SWITCH_UNSAFE", "target window has an active document; project creation was not attempted", source=source)
    response = _execute(client, create_project_program(friendly_name, project_name, description), target)
    if _write_status_unknown(response):
        return _error("WRITE_STATUS_UNKNOWN", "project creation timed out; list projects before retrying", window_id=target)
    if response.get("ok"):
        response.update({"created": True, "window_id": target})
    return response


def open_project(client, window_id, project_uuid, confirm_discard_unsaved=False):
    source, target, error = _raw_context(client, window_id)
    if error:
        return error
    if _active_document(source) and not confirm_discard_unsaved:
        return _error("DOCUMENT_SWITCH_UNSAFE", "opening a project can discard unsaved changes", source=source)
    response = _execute(client, open_project_program(project_uuid), target)
    if _write_status_unknown(response):
        return _error("WRITE_STATUS_UNKNOWN", "project open timed out; reread the window before retrying", window_id=target)
    return response


def create_schematic(client, window_id, name, confirm_discard_unsaved=False):
    source, target, error = _raw_context(client, window_id)
    if error:
        return error
    if not source.get("project_uuid"):
        return _error("SCHEMATIC_CONTEXT_UNAVAILABLE", "target window has no open project")
    if _active_document(source) and not confirm_discard_unsaved:
        return _error("DOCUMENT_SWITCH_UNSAFE", "creating and naming a schematic opens its default page", source=source)
    response = _execute(client, create_schematic_program(name), target)
    if _write_status_unknown(response):
        return _error("WRITE_STATUS_UNKNOWN", "schematic creation timed out; inspect the project tree before retrying", window_id=target)
    return response


def create_schematic_page(client, window_id, schematic_uuid, name):
    source, target, error = _raw_context(client, window_id)
    if error:
        return error
    if not source.get("project_uuid"):
        return _error("SCHEMATIC_CONTEXT_UNAVAILABLE", "target window has no open project")
    response = _execute(client, create_page_program(schematic_uuid, name), target)
    if _write_status_unknown(response):
        return _error("WRITE_STATUS_UNKNOWN", "page creation timed out; inspect the project tree before retrying", window_id=target)
    return response


def open_schematic_page(client, window_id, page_uuid, expected_context_revision, confirm_discard_unsaved=False):
    source, target, error = _raw_context(client, window_id)
    if error:
        return error
    current = context_revision(source)
    if current != expected_context_revision:
        return _error("CONTEXT_CHANGED", "EDA context changed before page open", expected=expected_context_revision, current=current)
    if _active_document(source) and source.get("document_uuid") != page_uuid and not confirm_discard_unsaved:
        return _error("DOCUMENT_SWITCH_UNSAFE", "opening another page may discard unsaved changes", source=source)
    response = _execute(client, open_page_program(page_uuid), target)
    if _write_status_unknown(response):
        return _error("WRITE_STATUS_UNKNOWN", "page open status is unknown; reread the window before retrying", window_id=target)
    return response


def _readback(before: dict, after: dict) -> dict:
    result = {}
    for kind in ("components", "wires", "labels", "ports", "flags", "no_connects"):
        key_of = (lambda item: item.get("id")) if kind != "no_connects" else (lambda item: (item.get("designator"), item.get("pin")))
        left = {key_of(item): item for item in before.get(kind, [])}
        right = {key_of(item): item for item in after.get(kind, [])}
        created = [right[key] for key in sorted(right.keys() - left)]
        deleted = [left[key] for key in sorted(left.keys() - right)]
        modified = [right[key] for key in sorted(left.keys() & right.keys()) if left[key] != right[key]]
        if created or deleted or modified:
            result[kind] = {"created": created, "modified": modified, "deleted": deleted}
    if before.get("page_format") != after.get("page_format"):
        result["page_format"] = {
            "before": before.get("page_format"),
            "after": after.get("page_format"),
        }
    return result


def _checked_write(client, window_id, expected_context_revision, expected_revision, program):
    before, target, error = _state(client, window_id)
    if error:
        return error
    if before["context_revision"] != expected_context_revision:
        return _error("CONTEXT_CHANGED", "EDA context changed since it was read", expected=expected_context_revision, current=before["context_revision"])
    if before["revision"] != expected_revision:
        return _error("STALE_SCHEMATIC", "schematic changed since it was read", expected=expected_revision, current=before["revision"])
    drc_before, error = _drc(client, target, before["source"].get("page_uuid"))
    if error:
        return _error("DRC_BASELINE_FAILED", "strict schematic DRC failed before the write", cause=error)
    response = _execute(client, guarded_program(before["source"], program, before), target)
    if _write_status_unknown(response):
        return _error("WRITE_STATUS_UNKNOWN", "bridge timed out during a schematic write; reread before retrying", context_revision=expected_context_revision, revision_before=expected_revision)
    if not response.get("ok"):
        return response
    mutation = response.get("result")
    if isinstance(mutation, dict) and mutation.get("__guard_error"):
        code = mutation["__guard_error"]
        return _error(code, "EDA context or schematic changed inside the write call", guard=mutation)
    after, _, error = _state(client, target)
    if error:
        return _error("WRITE_VERIFICATION_FAILED", "write returned but schematic readback failed", cause=error, mutation=mutation)
    drc_after, error = _drc(client, target, after["source"].get("page_uuid"))
    if error:
        return _error("WRITE_VERIFICATION_FAILED", "write returned but post-write DRC failed", cause=error, mutation=mutation)
    rows = mutation if isinstance(mutation, list) else [mutation]
    failures = [row for row in rows if isinstance(row, dict) and row.get("ok") is False]
    return {
        "ok": not failures,
        "code": "PARTIAL_APPLY" if failures else None,
        "applied": True,
        "partial": bool(failures),
        "context_revision": after["context_revision"],
        "revision_before": before["revision"],
        "revision_after": after["revision"],
        "results": rows,
        "readback": _readback(before, after),
        "topology": _topology_summary(after),
        "drc": schematic_drc_delta(drc_before, drc_after),
    }


def save_schematic(client, window_id, expected_context_revision, expected_revision):
    result = _checked_write(client, window_id, expected_context_revision, expected_revision, save_program())
    if result.get("ok") and not (result.get("results") or [{}])[0].get("saved"):
        return _error("SAVE_FAILED", "EasyEDA returned false while saving")
    return result


def set_schematic_page_format(
    client, window_id, expected_context_revision, expected_revision, sheet
):
    target, error = _window(client, window_id)
    if error:
        return error
    capability = _execute(
        client,
        "return typeof eda.dmt_Schematic?.modifySchematicPageTitleBlock === 'function';",
        target,
    )
    if not capability.get("ok"):
        return capability
    if capability.get("result") is not True:
        return _error(
            "API_UNAVAILABLE",
            "native schematic page title-block API is unavailable; no fallback primitives were created",
        )
    result = _checked_write(
        client,
        window_id,
        expected_context_revision,
        expected_revision,
        page_format_program(sheet),
    )
    failures = [
        row for row in result.get("results", [])
        if isinstance(row, dict) and row.get("ok") is False
    ]
    if failures:
        specific = str(failures[0].get("code") or "")
        if specific in {
            "PAGE_TITLE_BLOCK_UNAVAILABLE",
            "PAGE_SIZE_NOT_APPLIED",
            "PAGE_FORMAT_MISMATCH",
            "PAGE_FORMAT_WRITE_REJECTED",
        }:
            result["code"] = specific
        else:
            result["code"] = "WRITE_VERIFICATION_FAILED"
        result["message"] = {
            "PAGE_TITLE_BLOCK_UNAVAILABLE": (
                "the current EasyEDA page has no readable native titleBlockData"
            ),
            "PAGE_SIZE_NOT_APPLIED": (
                "the native title-block write returned, but the EasyEDA sheet structure "
                "does not match the requested A4/A3 size"
            ),
            "PAGE_FORMAT_MISMATCH": (
                "native title-block fields did not survive field-by-field readback"
            ),
            "PAGE_FORMAT_WRITE_REJECTED": (
                "EasyEDA rejected the native title-block update"
            ),
        }.get(result["code"], "native title-block write verification failed")
    return result


def _topology_summary(state: dict) -> dict:
    text = state.get("netlist")
    if not text:
        return {"available": False}
    from boardspec.exporters import parse_protel2_netlist

    parsed = parse_protel2_netlist(text)
    return {"available": True, "components": len(parsed["components"]), "nets": len(parsed["nets"]), "nodes": sum(len(value) for value in parsed["nets"].values())}


def get_schematic_summary(client, window_id=None, cursor=None, page_size=100):
    state, target, error = _state(client, window_id)
    if error:
        return error
    violations, error = _drc(client, target, state["source"].get("page_uuid"))
    if error:
        return error
    page, next_cursor = paginate(state["components"], cursor, page_size)
    return {
        "ok": True, "format": state["format"], "source": state["source"], "unit": "mil",
        "context_revision": state["context_revision"], "revision": state["revision"],
        "counts": {key: len(state.get(key, [])) for key in ("components", "wires", "labels", "ports", "flags", "no_connects")},
        "components": columnar(page, ["designator", "id", "name", "x", "y", "rotation", "mirror", "bbox"]),
        "page_format": state.get("page_format"),
        "topology": _topology_summary(state), "violations_by_type": dict(sorted(Counter(row["type"] for row in violations).items())),
        "next_cursor": next_cursor,
    }


def get_schematic_components(client, window_id=None, designators=None, region=None, include_pins=False):
    state, _, error = _state(client, window_id)
    if error:
        return error
    wanted = set(designators or [])
    rows = [item for item in state["components"] if (not wanted or item.get("designator") in wanted) and primitive_in_region(item, region)]
    missing = wanted - {item.get("designator") for item in rows}
    if missing:
        return _error("COMPONENT_NOT_FOUND", "components not found: " + ", ".join(sorted(missing, key=natural_key)))
    if not include_pins:
        rows = [{key: value for key, value in item.items() if key != "pins"} for item in rows]
    return {"ok": True, "format": state["format"], "source": state["source"], "unit": "mil", "context_revision": state["context_revision"], "revision": state["revision"], "components": rows}


def get_schematic_wiring(client, window_id=None, nets=None, region=None):
    state, _, error = _state(client, window_id)
    if error:
        return error
    wanted = set(nets or [])
    result = {key: [item for item in state[key] if (not wanted or item.get("net") in wanted) and primitive_in_region(item, region)] for key in ("wires", "labels", "ports", "flags")}
    return {"ok": True, "format": state["format"], "source": state["source"], "unit": "mil", "context_revision": state["context_revision"], "revision": state["revision"], **result}


def get_schematic_violations(client, window_id=None, ids=None, nets=None, region=None):
    state, target, error = _state(client, window_id)
    if error:
        return error
    all_rows, error = _drc(client, target, state["source"].get("page_uuid"))
    if error:
        return error
    wanted_ids, wanted_nets = set(ids or []), set(nets or [])
    rows = [row for row in all_rows if (not wanted_ids or row["id"] in wanted_ids) and (not wanted_nets or row.get("net") in wanted_nets) and primitive_in_region(row, region)]
    return {"ok": True, "format": state["format"], "source": state["source"], "context_revision": state["context_revision"], "revision": state["revision"], "passed": not all_rows, "total_count": len(all_rows), "matched_count": len(rows), "violations": rows}


def plan_schematic(spec_yaml, options=None):
    return build_plan(spec_yaml, options)


def resolve_schematic_plan(client, plan, window_id, expected_context_revision, expected_revision):
    state, _, error = _state(client, window_id)
    if error:
        return error
    if state["context_revision"] != expected_context_revision:
        return _error("CONTEXT_CHANGED", "EDA context changed before plan resolution")
    if state["revision"] != expected_revision:
        return _error("STALE_SCHEMATIC", "schematic changed before plan resolution")
    result = resolve_plan(plan, state)
    result.update({
        "context_revision": state["context_revision"],
        "revision": state["revision"],
    })
    return result


def diff_schematic_plan(client, plan, window_id, expected_context_revision, expected_revision):
    state, _, error = _state(client, window_id)
    if error:
        return error
    if state["context_revision"] != expected_context_revision:
        return _error("CONTEXT_CHANGED", "EDA context changed before plan diff")
    if state["revision"] != expected_revision:
        return _error("STALE_SCHEMATIC", "schematic changed before plan diff")
    result = diff_plan(plan, state)
    if plan.get("sheet"):
        result["page_format"] = _compare_page_format(
            plan["sheet"], state.get("page_format") or {}
        )
    result.update({"context_revision": state["context_revision"], "revision": state["revision"]})
    return result


def verify_schematic_topology(client, spec_yaml, window_id=None, base_dir=None):
    expected, error = expected_netlist(spec_yaml, base_dir)
    if error:
        return error
    generated_nets, error = expected_generated_nets(spec_yaml, base_dir)
    if error:
        return error
    state, _, error = _state(client, window_id)
    if error:
        return error
    if not state.get("netlist"):
        return _error("TOPOLOGY_UNAVAILABLE", "EasyEDA returned no Protel2 schematic netlist")
    result = compare_topology(expected, state["netlist"], generated_nets)
    result.update({"context_revision": state["context_revision"], "revision": state["revision"]})
    if not result["ok"]:
        result["code"] = "TOPOLOGY_MISMATCH"
    return result


def verify_schematic_readability(client, plan, window_id=None):
    state, _, error = _state(client, window_id)
    if error:
        return error
    result = verify_readability(plan, state)
    result.update({
        "context_revision": state["context_revision"],
        "revision": state["revision"],
    })
    return result


def _engineering_issue(code: str, **details) -> dict:
    stable = {"code": code, **details}
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"id": "sha256:" + hashlib.sha256(payload.encode()).hexdigest(), **stable}


def _compare_page_format(sheet: dict, current: dict) -> dict:
    expected_fields = page_format_fields(sheet)
    actual_fields = current.get("title_block_data") or {}
    mismatches = []
    for key, expected in expected_fields.items():
        actual = actual_fields.get(key)
        if actual is None:
            mismatches.append({"field": key, "expected": expected, "actual": None})
            continue
        if (
            "value" in expected
            and str(actual.get("value") or "") != str(expected.get("value") or "")
        ):
            mismatches.append({"field": key, "expected": expected, "actual": actual})
            continue
        if (
            bool(actual.get("show_title")) != bool(expected.get("showTitle"))
            or bool(actual.get("show_value")) != bool(expected.get("showValue"))
        ):
            mismatches.append({"field": key, "expected": expected, "actual": actual})

    expected_structure = page_format_structure(sheet)
    structural_mismatches = []

    def value(key):
        item = actual_fields.get(key)
        return item.get("value") if isinstance(item, dict) else None

    for key, expected in (
        ("Page Size", expected_structure["page_size"]),
        ("Size", expected_structure["size"]),
        ("Symbol", expected_structure["symbol"]),
        ("Border", expected_structure["border"]),
        ("Title Block", expected_structure["title_block"]),
        ("Title Block Position", expected_structure["title_block_position"]),
    ):
        actual = value(key)
        if str(actual or "") != str(expected):
            structural_mismatches.append(
                {"field": key, "expected": expected, "actual": actual}
            )
    for key in expected_structure["required_nonempty"]:
        actual = value(key)
        if actual is None or str(actual) == "":
            structural_mismatches.append(
                {"field": key, "expected": "non-empty native value", "actual": actual}
            )
    dimensions = {}
    for key, expected in (
        ("Width", expected_structure["width"]),
        ("Height", expected_structure["height"]),
    ):
        actual = value(key)
        try:
            number = float(actual)
        except (TypeError, ValueError):
            number = None
        if number is not None:
            dimensions[key.lower() + "_mil"] = number * 10.0
        if (
            number is None
            or abs(number - float(expected))
            > float(expected_structure["dimension_tolerance"])
        ):
            structural_mismatches.append({
                "field": key,
                "expected": expected,
                "tolerance": expected_structure["dimension_tolerance"],
                "actual": actual,
            })

    title_block_available = bool(actual_fields)
    show_title_block = bool(current.get("show_title_block"))
    return {
        "matches": (
            title_block_available
            and show_title_block
            and not mismatches
            and not structural_mismatches
        ),
        "show_title_block": show_title_block,
        "title_block_available": title_block_available,
        "mismatches": mismatches,
        "structural_mismatches": structural_mismatches,
        "live_dimensions": dimensions or None,
    }


def _box_distance(left: dict, right: dict) -> float:
    dx = max(left["minX"] - right["maxX"], right["minX"] - left["maxX"], 0)
    dy = max(left["minY"] - right["maxY"], right["minY"] - left["maxY"], 0)
    return max(dx, dy)


def _box_intersects(left: dict, right: dict) -> bool:
    return not (
        left["maxX"] <= right["minX"] or left["minX"] >= right["maxX"]
        or left["maxY"] <= right["minY"] or left["minY"] >= right["maxY"]
    )


def _inside_rect(box: dict, rect: dict) -> bool:
    return (
        box["minX"] >= rect["left"] and box["maxX"] <= rect["right"]
        and box["minY"] >= rect["top"] and box["maxY"] <= rect["bottom"]
    )


def verify_schematic_engineering_drawing(client, plan, window_id=None):
    if plan.get("format") != "schematic-plan/v0.2" or plan.get("phase") != "resolved":
        return _error(
            "PLAN_NOT_RESOLVED",
            "engineering drawing verification requires a resolved schematic-plan/v0.2",
        )
    sheet = plan.get("sheet")
    if not sheet:
        return _error("DRAWING_PROFILE_REQUIRED", "resolved plan has no engineering sheet")
    state, _, error = _state(client, window_id)
    if error:
        return error
    readability = verify_readability(plan, state)
    issues = list(readability.get("issues") or [])
    current_format = state.get("page_format") or {}
    page_comparison = _compare_page_format(sheet, current_format)
    if not page_comparison["title_block_available"]:
        issues.append(_engineering_issue("PAGE_TITLE_BLOCK_UNAVAILABLE"))
    elif not current_format.get("show_title_block"):
        issues.append(_engineering_issue("DRAWING_FRAME_MISSING"))
    for mismatch in page_comparison["mismatches"]:
        issues.append(_engineering_issue(
            "TITLE_BLOCK_FIELD_MISSING"
            if mismatch.get("actual") is None
            else "TITLE_BLOCK_FIELD_MISMATCH",
            **mismatch,
        ))
    for mismatch in page_comparison["structural_mismatches"]:
        issues.append(_engineering_issue("PAGE_SIZE_NOT_APPLIED", **mismatch))

    live_dimensions = page_comparison.get("live_dimensions") or {}
    width = live_dimensions.get("width_mil")
    height = live_dimensions.get("height_mil")
    if width is not None and height is not None:
        margin = float(sheet["border_margin_mil"])
        planned_title = sheet["title_block_rect"]
        title_width = float(planned_title["right"] - planned_title["left"])
        title_height = float(planned_title["bottom"] - planned_title["top"])
        usable = {
            "left": margin,
            "top": margin,
            "right": width - margin,
            "bottom": height - margin - title_height,
        }
        title = {
            "left": width - margin - title_width,
            "top": height - margin - title_height,
            "right": width - margin,
            "bottom": height - margin,
        }
    else:
        usable = sheet["usable_rect"]
        title = sheet["title_block_rect"]
    title_box = {
        "minX": title["left"], "maxX": title["right"],
        "minY": title["top"], "maxY": title["bottom"],
    }
    live_by_ref = {item.get("designator"): item for item in state.get("components", [])}
    planned_regions = {
        item["designator"]: (
            item["logical_path"].split("/", 1)[0]
            if "/" in item["logical_path"]
            else "root"
        )
        for item in plan.get("placements", [])
    }
    components = []
    for designator, region in planned_regions.items():
        item = live_by_ref.get(designator)
        box = (item or {}).get("bbox")
        if not box:
            issues.append(_engineering_issue("COMPONENT_BBOX_UNAVAILABLE", designator=designator))
            continue
        components.append((designator, region, box))
        if (
            box["minX"] < usable["left"] or box["maxX"] > usable["right"]
            or box["minY"] < usable["top"] or box["maxY"] > usable["bottom"]
        ):
            issues.append(_engineering_issue("COMPONENT_OUTSIDE_DRAWING_AREA", designator=designator))
        if not (
            box["maxX"] <= title_box["minX"] or box["minX"] >= title_box["maxX"]
            or box["maxY"] <= title_box["minY"] or box["minY"] >= title_box["maxY"]
        ):
            issues.append(_engineering_issue("TITLE_BLOCK_INTRUSION", designator=designator))
    for kind in ("labels", "ports", "flags"):
        for item in state.get(kind, []):
            box = item.get("bbox") or {
                "minX": item.get("x", 0), "maxX": item.get("x", 0),
                "minY": item.get("y", 0), "maxY": item.get("y", 0),
            }
            if not _inside_rect(box, usable):
                issues.append(_engineering_issue(
                    "PRIMITIVE_OUTSIDE_DRAWING_AREA", kind=kind[:-1],
                    primitive_id=item.get("id"),
                ))
            if _box_intersects(box, title_box):
                issues.append(_engineering_issue(
                    "TITLE_BLOCK_INTRUSION", kind=kind[:-1],
                    primitive_id=item.get("id"),
                ))
    for wire in state.get("wires", []):
        points = wire.get("points") or []
        if any(not (
            usable["left"] <= point.get("x", 0) <= usable["right"]
            and usable["top"] <= point.get("y", 0) <= usable["bottom"]
        ) for point in points):
            issues.append(_engineering_issue(
                "PRIMITIVE_OUTSIDE_DRAWING_AREA", kind="wire",
                primitive_id=wire.get("id"),
            ))
        if any(_box_intersects({
            "minX": min(left["x"], right["x"]),
            "maxX": max(left["x"], right["x"]),
            "minY": min(left["y"], right["y"]),
            "maxY": max(left["y"], right["y"]),
        }, title_box) for left, right in zip(points, points[1:])):
            issues.append(_engineering_issue(
                "TITLE_BLOCK_INTRUSION", kind="wire",
                primitive_id=wire.get("id"),
            ))
    required_gap = 400.0
    for index, (left_ref, left_region, left_box) in enumerate(components):
        for right_ref, right_region, right_box in components[index + 1:]:
            if left_region != right_region and _box_distance(left_box, right_box) < required_gap:
                issues.append(_engineering_issue(
                    "MODULE_SPACING_INSUFFICIENT",
                    components=sorted((left_ref, right_ref)),
                    required_mil=required_gap,
                ))
    unique = {item["id"]: item for item in issues}
    rows = sorted(unique.values(), key=lambda item: (item["code"], item["id"]))
    return {
        "ok": not rows,
        "passed": not rows,
        "format": state["format"],
        "source": state["source"],
        "context_revision": state["context_revision"],
        "revision": state["revision"],
        "sheet": sheet,
        "page_format": current_format,
        "page_format_comparison": page_comparison,
        "effective_usable_rect": usable,
        "visible_net_endpoint_coverage": readability.get("visible_net_endpoint_coverage"),
        "issues": rows,
    }


from .schematic_writes import (  # noqa: E402  (imports shared checked-write helpers)
    create_schematic_wires,
    edit_schematic_net_markers,
    edit_schematic_wires,
    place_schematic_components,
    place_schematic_net_flags,
    place_schematic_net_labels,
    place_schematic_net_ports,
    remove_schematic_components,
    set_schematic_component_placement,
    set_schematic_no_connects,
)
