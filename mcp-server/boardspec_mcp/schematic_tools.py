"""Public behavior for the single-page EasyEDA Schematic MCP."""
from __future__ import annotations

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
from .schematic_plan import build_plan, compare_topology, diff_plan, expected_netlist
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
    return flatten_schematic_drc(response.get("result") or [], page_uuid), None


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
    result.update({"context_revision": state["context_revision"], "revision": state["revision"]})
    return result


def verify_schematic_topology(client, spec_yaml, window_id=None, base_dir=None):
    expected, error = expected_netlist(spec_yaml, base_dir)
    if error:
        return error
    state, _, error = _state(client, window_id)
    if error:
        return error
    if not state.get("netlist"):
        return _error("TOPOLOGY_UNAVAILABLE", "EasyEDA returned no Protel2 schematic netlist")
    result = compare_topology(expected, state["netlist"])
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
