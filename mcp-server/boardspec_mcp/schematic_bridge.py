"""EasyEDA Pro bridge programs for deterministic schematic reads and writes."""

from __future__ import annotations

import json

from .bridge_client import BridgeClient
from .schematic_codec import to_eda
from .schematic_marker_bridge import marker_edit_program, marker_program


CAPTURE_SCHEMATIC_JS = r"""
const attempt = async (fn, fallback) => { try { return await fn(); } catch (_) { return fallback; } };
const mil = value => value === undefined || value === null ? null : Number(value) * 10;
const box = async item => {
  const value = await attempt(() => eda.sch_Primitive.getPrimitivesBBox([item]), null);
  return value ? {minX: mil(value.minX), minY: mil(value.minY), maxX: mil(value.maxX), maxY: mil(value.maxY)} : null;
};
const pointsOf = line => {
  const flat = line || [];
  const segments = Array.isArray(flat[0]) ? flat : Array.from({length: Math.floor(flat.length / 4)}, (_, i) => flat.slice(i * 4, i * 4 + 4));
  const edges = [], rawPoints = [];
  for (const segment of segments) {
    const points = [];
    for (let i = 0; i + 1 < segment.length; i += 2) points.push([Number(segment[i]), Number(segment[i + 1])]);
    if (points.length === 1) rawPoints.push(points[0]);
    for (let i = 0; i + 1 < points.length; i++) edges.push([points[i], points[i + 1]]);
  }
  if (!edges.length) return rawPoints.map(point => ({x: mil(point[0]), y: mil(point[1])}));
  const key = point => point[0] + ',' + point[1], adjacency = new Map();
  edges.forEach((edge, index) => edge.forEach((point, side) => {
    const value = adjacency.get(key(point)) || [];
    value.push({point: edge[1 - side], index}); adjacency.set(key(point), value);
  }));
  const ends = [...adjacency.entries()].filter(([, values]) => values.length === 1).map(([value]) => value).sort();
  let current = (ends[0] || [...adjacency.keys()].sort()[0]).split(',').map(Number);
  const ordered = [current], used = new Set();
  while (used.size < edges.length) {
    const choices = (adjacency.get(key(current)) || []).filter(value => !used.has(value.index))
      .sort((a, b) => key(a.point).localeCompare(key(b.point)));
    if (!choices.length) break;
    used.add(choices[0].index); current = choices[0].point; ordered.push(current);
  }
  const reverse = [...ordered].reverse();
  const result = JSON.stringify(reverse) < JSON.stringify(ordered) ? reverse : ordered;
  return result.filter((point, index) => !index || key(point) !== key(result[index - 1]))
    .map(point => ({x: mil(point[0]), y: mil(point[1])}));
};
const documentInfo = await attempt(() => eda.dmt_SelectControl.getCurrentDocumentInfo(), null);
const projectInfo = await attempt(() => eda.dmt_Project.getCurrentProjectInfo(), null);
const schematicItems = [];
for (const item of projectInfo?.data || []) {
  if (item?.schematic) schematicItems.push(item.schematic);
  else if (String(item?.itemType || '').includes('Schematic') && Array.isArray(item.page)) schematicItems.push(item);
}
let schematicInfo = null, pageInfo = null;
for (const schematic of schematicItems) {
  const page = (schematic.page || []).find(value => value.uuid === documentInfo?.uuid);
  if (page) { schematicInfo = schematic; pageInfo = page; break; }
}
const componentRaw = await attempt(() => eda.sch_PrimitiveComponent.getAll(), []);
const componentIds = new Set(componentRaw.map(item => item.getState_PrimitiveId()));
const components = [], ports = [], flags = [], noConnects = [];
for (const item of componentRaw) {
  const id = item.getState_PrimitiveId();
  const kind = String(await attempt(() => item.getState_ComponentType(), 'part')).toLowerCase();
  const otherProperty = await attempt(() => item.getState_OtherProperty(), null);
  const markerName = await attempt(() => item.getState_Name(), null);
  const directionValue = otherProperty?.direction ?? otherProperty?.Direction ?? otherProperty?.portDirection ?? markerName;
  const identificationValue = otherProperty?.identification ?? otherProperty?.Identification ?? otherProperty?.flagType ?? markerName;
  const direction = ['IN', 'OUT', 'BI'].includes(String(directionValue)) ? String(directionValue) : null;
  const identifications = ['Power', 'Ground', 'AnalogGround', 'ProtectGround'];
  const identification = identifications.includes(String(identificationValue)) ? String(identificationValue) : null;
  const base = {id, type: kind, net: await attempt(() => item.getState_Net(), null),
    x: mil(item.getState_X()), y: mil(item.getState_Y()), rotation: item.getState_Rotation(),
    mirror: item.getState_Mirror(), bbox: await box(item),
    direction, direction_status: direction ? 'readback' : 'unsupported',
    identification, identification_status: identification ? 'readback' : 'unsupported'};
  if (kind.includes('port')) { ports.push(base); continue; }
  if (kind.includes('flag')) { flags.push(base); continue; }
  const component = await attempt(() => item.getState_Component(), null);
  const symbol = await attempt(() => item.getState_Symbol(), null);
  const footprint = await attempt(() => item.getState_Footprint(), null);
  const pinRaw = await attempt(() => eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id), []);
  const pins = (pinRaw || []).map(pin => ({
    id: pin.primitiveId || pin.id || null, number: String(pin.pinNumber ?? ''),
    name: pin.pinName ?? '', type: pin.pinType ?? null,
    no_connected: Boolean(pin.noConnected), x: mil(pin.x), y: mil(pin.y),
    rotation: pin.rotation ?? null, sub_part_name: pin.subPartName ?? null
  }));
  const designator = await attempt(() => item.getState_Designator(), null);
  if (!designator) continue;
  for (const pin of pins) if (pin.no_connected) noConnects.push({designator, pin: '#' + pin.number});
  components.push({id, designator, name: item.getState_Name(),
    component, symbol, footprint, sub_part_name: await attempt(() => item.getState_SubPartName(), null),
    x: base.x, y: base.y, rotation: base.rotation, mirror: base.mirror, bbox: base.bbox, pins});
}
const wiresRaw = await attempt(() => eda.sch_PrimitiveWire.getAll(), []);
const wires = wiresRaw.map(item => ({id: item.getState_PrimitiveId(), net: item.getState_Net() || null,
  points: pointsOf(item.getState_Line()), line_width: item.getState_LineWidth(), line_type: item.getState_LineType()}))
  .filter(item => item.net || item.points.length >= 2);
const attrs = await attempt(() => eda.sch_PrimitiveAttribute.getAll(), []);
const labels = [];
for (const item of attrs) {
  const parent = await attempt(() => item.getState_ParentPrimitiveId(), null);
  if (parent && componentIds.has(parent)) continue;
  const key = await attempt(() => item.getState_Key(), '');
  const value = await attempt(() => item.getState_Value(), '');
  if (!value || (key && !String(key).toLowerCase().includes('net'))) continue;
  labels.push({id: item.getState_PrimitiveId(), parent_id: parent, key, net: value,
    x: mil(item.getState_X()), y: mil(item.getState_Y()), rotation: item.getState_Rotation()});
}
const nets = await attempt(() => eda.sch_Net.getAllNets(), []);
const netlist = await attempt(() => eda.sch_Netlist.getNetlist('Protel2'), null);
return {source: {project_uuid: projectInfo?.uuid || documentInfo?.parentProjectUuid || null,
  project_name: projectInfo?.name || projectInfo?.friendlyName || null,
  schematic_uuid: schematicInfo?.uuid || null, schematic_name: schematicInfo?.name || null,
  page_uuid: pageInfo?.uuid || documentInfo?.uuid || null, page_name: pageInfo?.name || null,
  document_uuid: documentInfo?.uuid || null, document_type: documentInfo?.documentType || null,
  tab_id: documentInfo?.tabId || null}, components, wires, labels, ports, flags,
  no_connects: noConnects, nets, netlist};
"""

WINDOW_CONTEXT_JS = r"""
const attempt = async (fn, fallback) => { try { return await fn(); } catch (_) { return fallback; } };
const documentInfo = await attempt(() => eda.dmt_SelectControl.getCurrentDocumentInfo(), null);
const projectInfo = await attempt(() => eda.dmt_Project.getCurrentProjectInfo(), null);
const schematicItems = [];
for (const item of projectInfo?.data || []) {
  if (item?.schematic) schematicItems.push(item.schematic);
  else if (String(item?.itemType || '').includes('Schematic') && Array.isArray(item.page)) schematicItems.push(item);
}
let schematicInfo = null, pageInfo = null;
for (const schematic of schematicItems) {
  const page = (schematic.page || []).find(value => value.uuid === documentInfo?.uuid);
  if (page) { schematicInfo = schematic; pageInfo = page; break; }
}
return {project_uuid: projectInfo?.uuid || documentInfo?.parentProjectUuid || null,
  project_name: projectInfo?.name || projectInfo?.friendlyName || null,
  schematic_uuid: schematicInfo?.uuid || null, schematic_name: schematicInfo?.name || null,
  page_uuid: pageInfo?.uuid || null, page_name: pageInfo?.name || null,
  document_uuid: documentInfo?.uuid || null, document_type: documentInfo?.documentType || null,
  tab_id: documentInfo?.tabId || null};
"""

CAPABILITY_PROBE_JS = r"""
return {
  editor_version: await eda.sys_Environment.getEditorCurrentVersion(true),
  api_present: {
    create_project: typeof eda.dmt_Project?.createProject === 'function',
    create_schematic: typeof eda.dmt_Schematic?.createSchematic === 'function',
    create_page: typeof eda.dmt_Schematic?.createSchematicPage === 'function',
    open_document: typeof eda.dmt_EditorControl?.openDocument === 'function',
    save: typeof eda.sch_Document?.save === 'function',
    component_create: typeof eda.sch_PrimitiveComponent?.create === 'function',
    wire_create: typeof eda.sch_PrimitiveWire?.create === 'function',
    net_label_create: typeof eda.sch_PrimitiveAttribute?.createNetLabel === 'function',
    net_port_create: typeof eda.sch_PrimitiveComponent?.createNetPort === 'function',
    net_flag_create: typeof eda.sch_PrimitiveComponent?.createNetFlag === 'function',
    netlist_read: typeof eda.sch_Netlist?.getNetlist === 'function',
    drc: typeof eda.sch_Drc?.check === 'function'
  }
};
"""


def _execute(client: BridgeClient, code: str, window_id: str | None = None) -> dict:
    try:
        return client.execute(code, window_id=window_id)
    except TypeError:  # backwards-compatible fake clients and third-party adapters
        return client.execute(code)


def capture_schematic(client: BridgeClient, window_id: str) -> dict:
    response = _execute(client, CAPTURE_SCHEMATIC_JS, window_id)
    if not response.get("ok"):
        return response
    result = response.get("result")
    if not isinstance(result, dict):
        return {"ok": False, "code": "SCHEMATIC_READ_FAILED", "message": "EasyEDA returned no schematic state"}
    source = result.get("source") or {}
    if not source.get("page_uuid") or source.get("document_type") not in {1, "1", "schematic", "Schematic", "SCHEMATIC"}:
        return {"ok": False, "code": "SCHEMATIC_CONTEXT_UNAVAILABLE", "message": "target window has no active schematic page"}
    return response


def capture_window_context(client: BridgeClient, window_id: str) -> dict:
    response = _execute(client, WINDOW_CONTEXT_JS, window_id)
    if not response.get("ok"):
        return response
    if not isinstance(response.get("result"), dict):
        return {"ok": False, "code": "SCHEMATIC_CONTEXT_UNAVAILABLE", "message": "EasyEDA returned no document context"}
    response["result"]["window_id"] = window_id
    return response


def _material_guard(state: dict) -> dict:
    unit = lambda value: round(to_eda(value), 6)
    components = [
        {
            "id": item.get("id"), "kind": "part", "designator": item.get("designator"),
            "net": None, "x": unit(item.get("x", 0)), "y": unit(item.get("y", 0)),
            "rotation": item.get("rotation"), "mirror": item.get("mirror"),
        }
        for item in state.get("components", [])
    ]
    for kind in ("ports", "flags"):
        components.extend(
            {
                "id": item.get("id"), "kind": kind[:-1], "designator": None,
                "net": item.get("net"), "x": unit(item.get("x", 0)),
                "y": unit(item.get("y", 0)), "rotation": item.get("rotation"),
                "mirror": item.get("mirror"),
            }
            for item in state.get(kind, [])
        )
    wires = [
        {
            "id": item.get("id"), "net": item.get("net"),
            "points": [[unit(p["x"]), unit(p["y"])] for p in item.get("points", [])],
        }
        for item in state.get("wires", [])
    ]
    labels = [
        {
            "id": item.get("id"), "net": item.get("net"),
            "x": unit(item.get("x", 0)), "y": unit(item.get("y", 0)),
        }
        for item in state.get("labels", [])
    ]
    return {
        "components": sorted(components, key=lambda item: item["id"] or ""),
        "wires": sorted(wires, key=lambda item: item["id"] or ""),
        "labels": sorted(labels, key=lambda item: item["id"] or ""),
        "no_connects": sorted(state.get("no_connects", []), key=lambda item: (item.get("designator") or "", item.get("pin") or "")),
    }


def guarded_program(source: dict, body: str, state: dict | None = None) -> str:
    """Recheck exact EDA context and material state inside the mutation call."""
    expected = {
        "project_uuid": source.get("project_uuid"),
        "document_uuid": source.get("document_uuid"),
        "tab_id": source.get("tab_id"),
    }
    material = _material_guard(state) if state is not None else None
    return r"""
const expectedContext = %s;
const expectedMaterial = %s;
const currentDocument = await eda.dmt_SelectControl.getCurrentDocumentInfo();
const currentProject = await eda.dmt_Project.getCurrentProjectInfo();
const actualContext = {project_uuid: currentProject?.uuid || currentDocument?.parentProjectUuid || null,
  document_uuid: currentDocument?.uuid || null, tab_id: currentDocument?.tabId || null};
if (JSON.stringify(expectedContext) !== JSON.stringify(actualContext)) {
  return {__guard_error: 'CONTEXT_CHANGED', expected: expectedContext, actual: actualContext};
}
if (expectedMaterial) {
  const number = value => Math.round(Number(value) * 1e6) / 1e6;
  const pointList = line => {
    const flat = line || [];
    const segments = Array.isArray(flat[0]) ? flat : Array.from({length: Math.floor(flat.length / 4)}, (_, i) => flat.slice(i * 4, i * 4 + 4));
    const edges = [], rawPoints = [];
    for (const segment of segments) {
      const points = [];
      for (let i = 0; i + 1 < segment.length; i += 2) points.push([number(segment[i]), number(segment[i + 1])]);
      if (points.length === 1) rawPoints.push(points[0]);
      for (let i = 0; i + 1 < points.length; i++) edges.push([points[i], points[i + 1]]);
    }
    if (!edges.length) return rawPoints;
    const key = point => point[0] + ',' + point[1], adjacency = new Map();
    edges.forEach((edge, index) => edge.forEach((point, side) => {
      const value = adjacency.get(key(point)) || [];
      value.push({point: edge[1 - side], index}); adjacency.set(key(point), value);
    }));
    const ends = [...adjacency.entries()].filter(([, values]) => values.length === 1).map(([value]) => value).sort();
    let current = (ends[0] || [...adjacency.keys()].sort()[0]).split(',').map(Number);
    const ordered = [current], used = new Set();
    while (used.size < edges.length) {
      const choices = (adjacency.get(key(current)) || []).filter(value => !used.has(value.index))
        .sort((a, b) => key(a.point).localeCompare(key(b.point)));
      if (!choices.length) break;
      used.add(choices[0].index); current = choices[0].point; ordered.push(current);
    }
    const reverse = [...ordered].reverse();
    const result = JSON.stringify(reverse) < JSON.stringify(ordered) ? reverse : ordered;
    return result.filter((point, index) => !index || key(point) !== key(result[index - 1]));
  };
  const rawComponents = await eda.sch_PrimitiveComponent.getAll();
  const components = [], noConnects = [];
  for (const item of rawComponents) {
    const rawKind = String(item.getState_ComponentType() || 'part').toLowerCase();
    const kind = rawKind.includes('port') ? 'port' : rawKind.includes('flag') ? 'flag' : 'part';
    const designator = item.getState_Designator() || null;
    if (kind === 'part' && !designator) continue;
    components.push({id: item.getState_PrimitiveId(), kind, designator,
      net: item.getState_Net() || null, x: number(item.getState_X()), y: number(item.getState_Y()),
      rotation: item.getState_Rotation(), mirror: item.getState_Mirror()});
    if (kind === 'part') for (const pin of await item.getAllPins() || []) {
      if (pin.getState_NoConnected()) noConnects.push({designator, pin: '#' + pin.getState_PinNumber()});
    }
  }
  const wires = (await eda.sch_PrimitiveWire.getAll()).map(item => ({id: item.getState_PrimitiveId(),
    net: item.getState_Net() || null, points: pointList(item.getState_Line())}))
    .filter(item => item.net || item.points.length >= 2);
  const componentIds = new Set(rawComponents.map(item => item.getState_PrimitiveId()));
  const labels = [];
  for (const item of await eda.sch_PrimitiveAttribute.getAll()) {
    const parent = item.getState_ParentPrimitiveId();
    if (parent && componentIds.has(parent)) continue;
    const key = item.getState_Key() || '', net = item.getState_Value() || '';
    if (net && (!key || String(key).toLowerCase().includes('net'))) labels.push({id: item.getState_PrimitiveId(),
      net, x: number(item.getState_X()), y: number(item.getState_Y())});
  }
  const actualMaterial = {components: components.sort((a,b) => a.id.localeCompare(b.id)),
    wires: wires.sort((a,b) => a.id.localeCompare(b.id)), labels: labels.sort((a,b) => a.id.localeCompare(b.id)),
    no_connects: noConnects.sort((a,b) => (a.designator + a.pin).localeCompare(b.designator + b.pin))};
  if (JSON.stringify(expectedMaterial) !== JSON.stringify(actualMaterial)) {
    return {__guard_error: 'STALE_SCHEMATIC'};
  }
}
%s
""" % (_js(expected), _js(material), body)


def run_strict_drc(client: BridgeClient, window_id: str) -> dict:
    return _execute(client, "return await eda.sch_Drc.check(true, false, true);", window_id)


def _js(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def create_project_program(friendly_name: str, project_name: str | None, description: str | None) -> str:
    return f"""
const uuid = await eda.dmt_Project.createProject({_js(friendly_name)}, {_js(project_name)}, undefined, undefined, {_js(description)});
if (!uuid) throw new Error('createProject returned no UUID');
await new Promise(resolve => setTimeout(resolve, 1500));
return {{uuid, info: await eda.dmt_Project.getProjectInfo(uuid)}};
"""


def open_project_program(project_uuid: str) -> str:
    return f"return {{opened: Boolean(await eda.dmt_Project.openProject({_js(project_uuid)})), project_uuid: {_js(project_uuid)}}};"


def create_schematic_program(name: str) -> str:
    return f"""
const uuid = await eda.dmt_Schematic.createSchematic();
if (!uuid) throw new Error('createSchematic returned no UUID');
await new Promise(resolve => setTimeout(resolve, 1500));
const info = await eda.dmt_Schematic.getSchematicInfo(uuid);
const page = info?.page?.[0];
if (!page) throw new Error('created schematic has no default page');
await eda.dmt_EditorControl.openDocument(page.uuid);
await new Promise(resolve => setTimeout(resolve, 750));
if (!await eda.dmt_Schematic.modifySchematicName(uuid, {_js(name)})) throw new Error('schematic rename failed');
await new Promise(resolve => setTimeout(resolve, 1000));
const renamed = await eda.dmt_Schematic.getSchematicInfo(uuid);
if (renamed?.name !== {_js(name)}) throw new Error('schematic rename did not persist');
return {{uuid, page_uuid: page.uuid, info: renamed}};
"""


def create_page_program(schematic_uuid: str, name: str) -> str:
    return f"""
const uuid = await eda.dmt_Schematic.createSchematicPage({_js(schematic_uuid)});
if (!uuid) throw new Error('createSchematicPage returned no UUID');
await new Promise(resolve => setTimeout(resolve, 1000));
if (!await eda.dmt_Schematic.modifySchematicPageName(uuid, {_js(name)})) throw new Error('page rename failed');
await new Promise(resolve => setTimeout(resolve, 1000));
const renamed = await eda.dmt_Schematic.getSchematicPageInfo(uuid);
if (renamed?.name !== {_js(name)}) throw new Error('page rename did not persist');
return {{uuid, info: renamed}};
"""


def open_page_program(page_uuid: str) -> str:
    return f"return {{tab_id: await eda.dmt_EditorControl.openDocument({_js(page_uuid)}), page_uuid: {_js(page_uuid)}}};"


def save_program() -> str:
    return "return {saved: Boolean(await eda.sch_Document.save())};"


def component_create_program(placements: list[dict]) -> str:
    encoded = []
    for item in placements:
        encoded.append({**item, "x": to_eda(item["x"]), "y": to_eda(item["y"])})
    return r"""
const placements = %s, results = [];
for (const item of placements) {
  try {
    let value = await eda.sch_PrimitiveComponent.create({libraryUuid: item.library_uuid, uuid: item.device_uuid},
      item.x, item.y, item.sub_part_name, item.rotation, item.mirror, true, true);
    if (!value) throw new Error('component create returned no object');
    if (value.getState_Designator() !== item.designator) value = await eda.sch_PrimitiveComponent.modify(
      value.getState_PrimitiveId(), {designator: item.designator});
    results.push({ok: true, client_id: item.client_id, id: value.getState_PrimitiveId(), designator: value.getState_Designator()});
  } catch (error) { results.push({ok: false, client_id: item.client_id, message: String(error)}); }
}
return results;
""" % _js(encoded)


def component_edit_program(edits: list[dict]) -> str:
    encoded = []
    for item in edits:
        props = {key: value for key, value in item["properties"].items()}
        for key in ("x", "y"):
            if key in props:
                props[key] = to_eda(props[key])
        encoded.append({"id": item["id"], "designator": item["designator"], "properties": props})
    return r"""
const edits = %s, results = [];
for (const item of edits) { try {
  const value = await eda.sch_PrimitiveComponent.modify(item.id, item.properties);
  if (!value) throw new Error('component modify returned no object');
  results.push({ok: true, id: item.id, designator: value.getState_Designator()});
} catch (error) { results.push({ok: false, id: item.id, message: String(error)}); } }
return results;
""" % _js(encoded)


def component_remove_program(ids: list[str]) -> str:
    return f"return [{{ok: Boolean(await eda.sch_PrimitiveComponent.delete({_js(ids)})), op: 'delete', ids: {_js(ids)}}}];"


def wire_create_program(items: list[dict]) -> str:
    encoded = []
    for item in items:
        encoded.append({**item, "points": [[to_eda(p["x"]), to_eda(p["y"])] for p in item["points"]]})
    return r"""
const items = %s, results = [];
for (const item of items) { try {
  const line = item.points.flat();
  const value = await eda.sch_PrimitiveWire.create(line, item.net);
  if (!value) throw new Error('wire create returned no object');
  results.push({ok: true, client_id: item.client_id, id: value.getState_PrimitiveId(), net: value.getState_Net()});
} catch (error) { results.push({ok: false, client_id: item.client_id, message: String(error)}); } }
return results;
""" % _js(encoded)


def wire_edit_program(actions: list[dict]) -> str:
    encoded = []
    for action in actions:
        value = dict(action)
        props = dict(value.get("properties") or {})
        if props.get("points") is not None:
            props["line"] = [
                coordinate
                for point in props.pop("points")
                for coordinate in (to_eda(point["x"]), to_eda(point["y"]))
            ]
        value["properties"] = props
        encoded.append(value)
    return r"""
const actions = %s, results = [];
for (const item of actions) { try {
  const value = item.op === 'delete' ? await eda.sch_PrimitiveWire.delete(item.id)
    : await eda.sch_PrimitiveWire.modify(item.id, item.properties || {});
  if (!value) throw new Error('wire ' + item.op + ' returned no result');
  results.push({ok: true, op: item.op, id: item.id});
} catch (error) { results.push({ok: false, op: item.op, id: item.id, message: String(error)}); } }
return results;
""" % _js(encoded)


def no_connect_program(edits: list[dict]) -> str:
    return r"""
const edits = %s, components = await eda.sch_PrimitiveComponent.getAll(), results = [];
for (const edit of edits) {
  const matches = components.filter(item => item.getState_Designator() === edit.designator);
  if (matches.length !== 1) { results.push({ok: false, designator: edit.designator, message: 'component match count ' + matches.length}); continue; }
  const pins = await matches[0].getAllPins() || [];
  for (const selector of edit.pin_selectors) {
    const pin = pins.find(value => '#' + value.getState_PinNumber() === selector);
    if (!pin) { results.push({ok: false, designator: edit.designator, pin: selector, message: 'pin not found'}); continue; }
    if (!pin.getState_NoConnected()) { const pending = pin.toAsync(); pending.setState_NoConnected(true); await pending.done(); }
    results.push({ok: true, designator: edit.designator, pin: selector});
  }
}
return results;
""" % _js(edits)
