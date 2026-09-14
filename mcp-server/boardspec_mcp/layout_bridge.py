"""EasyEDA Pro JavaScript bridge programs for PCB layout tools."""

from __future__ import annotations

import json

from .bridge_client import BridgeClient


CAPTURE_LAYOUT_JS = r"""
const attempt = async (fn, fallback) => { try { return await fn(); } catch (_) { return fallback; } };
const bboxOf = async (primitive) => {
  const value = await attempt(() => eda.pcb_Primitive.getPrimitivesBBox([primitive]), null);
  return value || null;
};
const polygonSource = (polygon) => {
  if (!polygon) return null;
  try { return polygon.getSource(); } catch (_) { return null; }
};
const documentInfo = await attempt(() => eda.dmt_SelectControl.getCurrentDocumentInfo(), null);
const componentsRaw = await eda.pcb_PrimitiveComponent.getAll();
const components = [];
for (const component of componentsRaw) {
  const pinsRaw = await attempt(() => component.getAllPins(), []);
  const pins = [];
  for (const pin of pinsRaw || []) {
    pins.push({
      id: pin.getState_PrimitiveId(),
      number: pin.getState_PadNumber(),
      net: pin.getState_Net(),
      layer: pin.getState_Layer(),
      x: pin.getState_X(),
      y: pin.getState_Y(),
      rotation: pin.getState_Rotation(),
      bbox: await bboxOf(pin)
    });
  }
  components.push({
    id: component.getState_PrimitiveId(),
    designator: component.getState_Designator(),
    name: component.getState_Name(),
    footprint: component.getState_Footprint(),
    layer: component.getState_Layer(),
    x: component.getState_X(),
    y: component.getState_Y(),
    rotation: component.getState_Rotation(),
    locked: component.getState_PrimitiveLock(),
    pads: pins,
    pad_nets: component.getState_Pads(),
    bbox: await bboxOf(component)
  });
}
const linesRaw = await eda.pcb_PrimitiveLine.getAll();
const lines = linesRaw.map(item => ({
  id: item.getState_PrimitiveId(), net: item.getState_Net(), layer: item.getState_Layer(),
  start_x: item.getState_StartX(), start_y: item.getState_StartY(),
  end_x: item.getState_EndX(), end_y: item.getState_EndY(),
  width: item.getState_LineWidth(), locked: item.getState_PrimitiveLock()
}));
const arcsRaw = await eda.pcb_PrimitiveArc.getAll();
const arcs = arcsRaw.map(item => ({
  id: item.getState_PrimitiveId(), net: item.getState_Net(), layer: item.getState_Layer(),
  start_x: item.getState_StartX(), start_y: item.getState_StartY(),
  end_x: item.getState_EndX(), end_y: item.getState_EndY(), angle: item.getState_ArcAngle(),
  width: item.getState_LineWidth(), locked: item.getState_PrimitiveLock()
}));
const viasRaw = await eda.pcb_PrimitiveVia.getAll();
const vias = viasRaw.map(item => ({
  id: item.getState_PrimitiveId(), net: item.getState_Net(), x: item.getState_X(),
  y: item.getState_Y(), hole_diameter: item.getState_HoleDiameter(),
  diameter: item.getState_Diameter(), via_type: item.getState_ViaType(),
  blind_via_rule: item.getState_DesignRuleBlindViaName(), locked: item.getState_PrimitiveLock()
}));
const polylinesRaw = await eda.pcb_PrimitivePolyline.getAll();
const polylines = [];
for (const item of polylinesRaw) polylines.push({
  id: item.getState_PrimitiveId(), net: item.getState_Net(), layer: item.getState_Layer(),
  polygon: polygonSource(item.getState_Polygon()), width: item.getState_LineWidth(),
  locked: item.getState_PrimitiveLock(), bbox: await bboxOf(item)
});
const poursRaw = await eda.pcb_PrimitivePour.getAll();
const pours = [];
for (const item of poursRaw) pours.push({
  id: item.getState_PrimitiveId(), net: item.getState_Net(), layer: item.getState_Layer(),
  polygon: polygonSource(item.getState_ComplexPolygon()), fill_method: item.getState_PourFillMethod(),
  preserve_islands: item.getState_PreserveSilos(), name: item.getState_PourName(),
  priority: item.getState_PourPriority(), width: item.getState_LineWidth(),
  locked: item.getState_PrimitiveLock(), bbox: await bboxOf(item)
});
const pouredRaw = await attempt(() => eda.pcb_PrimitivePoured.getAll(), []);
const poured = [];
for (const item of pouredRaw) poured.push({
  id: item.getState_PrimitiveId(), pour_id: item.getState_PourPrimitiveId(),
  fills: (item.getState_PourFills() || []).map(fill => ({
    id: fill.id, polygon: polygonSource(fill.path), line_width: fill.lineWidth,
    fill: fill.fill
  })),
  bbox: await bboxOf(item)
});
const regionsRaw = await eda.pcb_PrimitiveRegion.getAll();
const regions = [];
for (const item of regionsRaw) regions.push({
  id: item.getState_PrimitiveId(), layer: item.getState_Layer(),
  polygon: polygonSource(item.getState_ComplexPolygon()), rule_types: item.getState_RuleType(),
  name: item.getState_RegionName(), width: item.getState_LineWidth(),
  locked: item.getState_PrimitiveLock(), bbox: await bboxOf(item)
});
const obstacleGroups = await Promise.all([
  attempt(() => eda.pcb_PrimitiveFill.getAll(), []),
  attempt(() => eda.pcb_PrimitivePad.getAll(), []),
  attempt(() => eda.pcb_PrimitiveObject.getAll(), []),
  attempt(() => eda.pcb_PrimitiveImage.getAll(), []),
  attempt(() => eda.pcb_PrimitiveDimension.getAll(), []),
  attempt(() => eda.pcb_PrimitiveString.getAll(), [])
]);
const obstacles = [];
const knownPadIds = new Set(components.flatMap(component => component.pads.map(pad => pad.id)));
const seenObstacleIds = new Set();
for (const primitive of obstacleGroups.flat()) {
  const id = primitive.getState_PrimitiveId();
  if (knownPadIds.has(id) || seenObstacleIds.has(id)) continue;
  seenObstacleIds.add(id);
  obstacles.push({
    id,
    type: primitive.getState_PrimitiveType(),
    bbox: await bboxOf(primitive)
  });
}
const layers = await attempt(() => eda.pcb_Layer.getAllLayers(), []);
const stacking = await attempt(() => eda.pcb_Layer.getCurrentPhysicalStackingConfiguration(), null);
const rules = await attempt(() => eda.pcb_Drc.getCurrentRuleConfiguration(), null);
const netClasses = await attempt(() => eda.pcb_Drc.getAllNetClasses(), []);
const differentialPairs = await attempt(() => eda.pcb_Drc.getAllDifferentialPairs(), []);
const nets = await attempt(() => eda.pcb_Net.getAllNets(), []);
return {
  document: documentInfo ? {
    uuid: documentInfo.uuid, type: documentInfo.documentType,
    tab_id: documentInfo.tabId, project_uuid: documentInfo.parentProjectUuid,
    library_uuid: documentInfo.parentLibraryUuid
  } : null,
  layers, stacking, rules, net_classes: netClasses,
  differential_pairs: differentialPairs, nets, components, lines, arcs,
  vias, polylines, pours, poured, regions, obstacles
};
"""


def capture_layout(client: BridgeClient) -> dict:
    response = client.execute(CAPTURE_LAYOUT_JS)
    if not response.get("ok"):
        return response
    if not isinstance(response.get("result"), dict):
        return {
            "ok": False,
            "code": "LAYOUT_READ_FAILED",
            "message": "EasyEDA returned no PCB layout state",
        }
    document = response["result"].get("document") or {}
    if not document.get("uuid") or document.get("type") not in {3, "pcb", "PCB"}:
        return {
            "ok": False,
            "code": "NO_ACTIVE_PCB",
            "message": "the focused EasyEDA document is not an active PCB",
        }
    return response


def run_strict_drc(client: BridgeClient) -> dict:
    return client.execute("return await eda.pcb_Drc.check(true, false, true);")


def placement_program(edits: list[dict]) -> str:
    return r"""
const edits = %s;
const results = [];
for (const edit of edits) {
  try {
    const changed = await eda.pcb_PrimitiveComponent.modify(edit.id, edit.properties);
    if (!changed) throw new Error('component modify returned no object');
    const value = await eda.pcb_PrimitiveComponent.get(edit.id);
    results.push({ok: true, id: edit.id, designator: value.getState_Designator(),
      x: value.getState_X(), y: value.getState_Y(), layer: value.getState_Layer(),
      rotation: value.getState_Rotation(), locked: value.getState_PrimitiveLock()});
  } catch (error) {
    results.push({ok: false, id: edit.id, message: String(error)});
  }
}
return results;
""" % json.dumps(
        edits, ensure_ascii=False
    )


def auto_layout_program() -> str:
    return "return await eda.pcb_Document.autoLayout();"


def auto_routing_program(props: dict) -> str:
    return "return await eda.pcb_Document.autoRouting(" + json.dumps(props) + ");"


def create_route_program(net: str, operations: list[dict]) -> str:
    return r"""
const net = %s;
const operations = %s;
const results = [];
for (const op of operations) {
  try {
    let value;
    if (op.type === 'line') {
      value = await eda.pcb_PrimitiveLine.create(net, op.layer, op.start_x, op.start_y,
        op.end_x, op.end_y, op.width === null ? undefined : op.width, false);
    } else {
      value = await eda.pcb_PrimitiveVia.create(net, op.x, op.y, op.hole_diameter,
        op.diameter, op.via_type || 0, op.blind_via_rule || null, null, false);
    }
    if (!value) throw new Error(op.type + ' create returned no object');
    results.push({ok: true, type: op.type, id: value.getState_PrimitiveId()});
  } catch (error) {
    results.push({ok: false, type: op.type, message: String(error)});
  }
}
return results;
""" % (
        json.dumps(net),
        json.dumps(operations, ensure_ascii=False),
    )


def edit_routing_program(actions: list[dict]) -> str:
    return r"""
const actions = %s;
const apis = {line: eda.pcb_PrimitiveLine, arc: eda.pcb_PrimitiveArc, via: eda.pcb_PrimitiveVia};
const results = [];
for (const action of actions) {
  try {
    const api = apis[action.type];
    let value;
    if (action.op === 'delete') value = await api.delete([action.id]);
    else value = await api.modify(action.id, action.properties || {});
    if (!value) throw new Error(action.op + ' returned false');
    results.push({ok: true, op: action.op, type: action.type, id: action.id});
  } catch (error) {
    results.push({ok: false, op: action.op, type: action.type, id: action.id, message: String(error)});
  }
}
return results;
""" % json.dumps(
        actions, ensure_ascii=False
    )


def outline_program(
    contours: list[list[dict]], replace: bool, outline_ids: dict
) -> str:
    return r"""
const contours = %s;
const replace = %s;
const existing = %s;
const results = [];
if (replace) {
  for (const [type, ids] of Object.entries(existing)) {
    if (!ids.length) continue;
    try {
      const api = type === 'line' ? eda.pcb_PrimitiveLine : type === 'arc' ? eda.pcb_PrimitiveArc : eda.pcb_PrimitivePolyline;
      const ok = await api.delete(ids);
      results.push({ok: Boolean(ok), op: 'delete', type, ids});
    } catch (error) {
      results.push({ok: false, op: 'delete', type, ids, message: String(error)});
    }
  }
}
for (const contour of contours) {
  try {
    // EasyEDA Pro 3.2.186 rejects PrimitiveLine.create on BoardOutline but
    // accepts a closed PrimitivePolyline. One primitive per contour also makes
    // replacement/readback unambiguous.
    const source = [contour[0].x, contour[0].y, 'L'];
    for (let i = 1; i < contour.length; i++) source.push(contour[i].x, contour[i].y);
    source.push(contour[0].x, contour[0].y);
    const polygon = eda.pcb_MathPolygon.createPolygon(source);
    if (!polygon) throw new Error('invalid outline polygon source');
    const width = contour.find(point => point.width !== undefined && point.width !== null)?.width ?? 5;
    const value = await eda.pcb_PrimitivePolyline.create('', 11, polygon, width, false);
    results.push(value ? {ok: true, op: 'create', type: 'polyline', id: value.getState_PrimitiveId()}
      : {ok: false, op: 'create', type: 'polyline', message: 'create returned no object'});
  } catch (error) {
    results.push({ok: false, op: 'create', type: 'polyline', message: String(error)});
  }
}
return results;
""" % (
        json.dumps(contours, ensure_ascii=False),
        "true" if replace else "false",
        json.dumps(outline_ids),
    )


def region_program(actions: list[dict]) -> str:
    return r"""
const actions = %s;
const results = [];
for (const action of actions) {
  try {
    let value;
    if (action.op === 'delete') {
      value = await eda.pcb_PrimitiveRegion.delete([action.id]);
    } else {
      if (action.op === 'create') {
        const polygon = eda.pcb_MathPolygon.createPolygon(action.polygon);
        if (!polygon) throw new Error('invalid polygon source');
        value = await eda.pcb_PrimitiveRegion.create(action.layer, polygon,
          action.rule_types || [], action.name, action.width, Boolean(action.locked));
      } else {
        const properties = {...(action.properties || {})};
        if (action.polygon) {
          const polygon = eda.pcb_MathPolygon.createPolygon(action.polygon);
          if (!polygon) throw new Error('invalid polygon source');
          properties.complexPolygon = polygon;
        }
        value = await eda.pcb_PrimitiveRegion.modify(action.id, properties);
      }
    }
    if (!value) throw new Error(action.op + ' returned false');
    results.push({ok: true, op: action.op, id: action.id || value.getState_PrimitiveId()});
  } catch (error) {
    results.push({ok: false, op: action.op, id: action.id, message: String(error)});
  }
}
return results;
""" % json.dumps(
        actions, ensure_ascii=False
    )


def pour_program(actions: list[dict], rebuild: bool) -> str:
    return r"""
const actions = %s;
const rebuild = %s;
const results = [];
const rebuildIds = [];
for (const action of actions) {
  try {
    let value;
    if (action.op === 'delete') {
      value = await eda.pcb_PrimitivePour.delete([action.id]);
    } else {
      if (action.op === 'create') {
        const polygon = eda.pcb_MathPolygon.createPolygon(action.polygon);
        if (!polygon) throw new Error('invalid polygon source');
        value = await eda.pcb_PrimitivePour.create(action.net, action.layer, polygon,
          action.fill_method, action.preserve_islands, action.name,
          action.priority, action.width, action.locked);
      } else {
        const properties = {...(action.properties || {})};
        if (action.polygon) {
          const polygon = eda.pcb_MathPolygon.createPolygon(action.polygon);
          if (!polygon) throw new Error('invalid polygon source');
          properties.complexPolygon = polygon;
        }
        value = await eda.pcb_PrimitivePour.modify(action.id, properties);
      }
    }
    if (!value) throw new Error(action.op + ' returned false');
    const id = action.id || value.getState_PrimitiveId();
    if (action.op !== 'delete') rebuildIds.push(id);
    results.push({ok: true, op: action.op, id});
  } catch (error) {
    results.push({ok: false, op: action.op, id: action.id, message: String(error)});
  }
}
if (rebuild && rebuildIds.length) {
  let rebuiltCount = 0;
  for (const id of rebuildIds) {
    try {
      // Rebuild belongs to the individual IPCB_PrimitivePour instance in
      // EasyEDA Pro 3.2.186, not the static primitive collection API.
      const pour = await eda.pcb_PrimitivePour.get(id);
      if (!pour) throw new Error('pour readback returned no object');
      const rebuilt = await pour.rebuildCopperRegion();
      if (!rebuilt) throw new Error('rebuild returned no poured region');
      rebuiltCount += 1;
    } catch (error) {
      results.push({ok: false, op: 'rebuild', id, message: String(error)});
    }
  }
  if (rebuiltCount) results.push({ok: true, op: 'rebuild', count: rebuiltCount});
}
return results;
""" % (
        json.dumps(actions, ensure_ascii=False),
        "true" if rebuild else "false",
    )
