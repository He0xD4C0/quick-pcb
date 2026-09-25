"""EasyEDA JavaScript programs for schematic net markers."""

from __future__ import annotations

import json

from .schematic_codec import to_eda


def _js(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _encode_rotation(value: float | int) -> float:
    """Convert plan rotation to the marker API's counter-rotating convention."""
    return (360 - value) % 360


def marker_program(kind: str, items: list[dict]) -> str:
    encoded = [{
        **item,
        "x": to_eda(item["x"]),
        "y": to_eda(item["y"]),
        "rotation": _encode_rotation(item.get("rotation", 0)),
    } for item in items]
    calls = {
        "label": "eda.sch_PrimitiveAttribute.createNetLabel(item.x, item.y, item.net)",
        "port": "eda.sch_PrimitiveComponent.createNetPort(item.direction, item.net, item.x, item.y, item.rotation, item.mirror)",
        "flag": "eda.sch_PrimitiveComponent.createNetFlag(item.identification, item.net, item.x, item.y, item.rotation, item.mirror)",
    }
    return r"""
const items = %s, results = [];
for (const item of items) { try {
  const value = await %s;
  if (!value) throw new Error('%s create returned no object');
  results.push({ok: true, client_id: item.client_id, id: value.getState_PrimitiveId(), net: item.net});
} catch (error) { results.push({ok: false, client_id: item.client_id, message: String(error)}); } }
return results;
""" % (_js(encoded), calls[kind], kind)


def marker_edit_program(actions: list[dict]) -> str:
    encoded = []
    for action in actions:
        value = dict(action)
        replacement = dict(value.get("replacement") or {})
        point = replacement.pop("at", None)
        if point:
            replacement["x"] = to_eda(point["x"])
            replacement["y"] = to_eda(point["y"])
        replacement["rotation"] = _encode_rotation(replacement.get("rotation", 0))
        value["replacement"] = replacement or None
        encoded.append(value)
    return r"""
const actions = %s, results = [];
const createMarker = async item => {
  if (item.kind === 'label') return await eda.sch_PrimitiveAttribute.createNetLabel(item.x, item.y, item.net);
  if (item.kind === 'port') return await eda.sch_PrimitiveComponent.createNetPort(item.direction, item.net, item.x, item.y, item.rotation, item.mirror);
  return await eda.sch_PrimitiveComponent.createNetFlag(item.identification, item.net, item.x, item.y, item.rotation, item.mirror);
};
const deleteMarker = async (kind, id) => kind === 'label'
  ? await eda.sch_PrimitiveAttribute.delete(id)
  : await eda.sch_PrimitiveComponent.delete(id);
for (const action of actions) { try {
  if (action.op === 'delete') {
    if (!await deleteMarker(action.kind, action.id)) throw new Error('marker delete returned false');
    results.push({ok: true, op: 'delete', kind: action.kind, id: action.id});
    continue;
  }
  const created = await createMarker(action.replacement);
  if (!created) throw new Error('replacement create returned no object');
  const newId = created.getState_PrimitiveId();
  if (!await deleteMarker(action.kind, action.id)) {
    await deleteMarker(action.kind, newId);
    throw new Error('old marker delete failed; replacement rollback attempted');
  }
  results.push({ok: true, op: 'replace', kind: action.kind, id: action.id, new_id: newId});
} catch (error) { results.push({ok: false, op: action.op, kind: action.kind, id: action.id, message: String(error)}); } }
return results;
""" % _js(encoded)
