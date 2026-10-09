#!/usr/bin/env python3
"""Read, geometrically verify, and optionally save/export the amplifier page.

Never moves components or rebuilds wiring. Export requires --export.
"""
import argparse
import base64
import hashlib
import json
import zipfile
from pathlib import Path

from boardspec.core import build_flat, process
from boardspec.exporters import render_bom_csv, render_mermaid, render_protel2_netlist
from boardspec_mcp.bridge_client import BridgeClient
from boardspec_mcp.schematic_readability import _segment_hits_box, _intersects
from boardspec_mcp.schematic_tools import _state, get_schematic_violations, save_schematic, verify_schematic_topology

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / 'examples/s8050-s8550-audio-amplifier'
SPEC = DESIGN / 'S8050_S8550_Audio_Amplifier.yaml'


def point(p):
    return (round(p['x'], 6), round(p['y'], 6))


def on_segment(p, a, b):
    return (a[0] == b[0] == p[0] and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])) or (a[1] == b[1] == p[1] and min(a[0], b[0]) <= p[0] <= max(a[0], b[0]))


def geometry(state, nets):
    pin_net = {f'{ref}.#{pin}': n['name'] for n in nets for ref, pin in n['nodes']}
    pins = {f"{c['designator']}.#{p['number']}": point(p) for c in state['components'] for p in c['pins']}
    markers = state['ports'] + state['flags']
    edges, issues = [], []
    for wire in state['wires']:
        paths = wire.get('segments') or [wire['points']]
        pairs = [(point(a), point(b)) for path in paths for a, b in zip(path, path[1:])]
        names = {pin_net[ref] for ref, p in pins.items() if any(on_segment(p, a, b) for a, b in pairs)}
        names |= {m['net'] for m in markers if any(on_segment(point(m), a, b) for a, b in pairs)}
        if wire.get('net'):
            names.add(wire['net'])
        if len(names) != 1:
            issues.append({'code': 'WIRE_NET_AMBIGUOUS', 'wire': wire['id'], 'nets': sorted(names)})
            continue
        net = next(iter(names))
        for a, b in pairs:
            edges.append((net, a, b))
            if a[0] != b[0] and a[1] != b[1]:
                issues.append({'code': 'NON_ORTHOGONAL', 'wire': wire['id']})
            for c in state['components']:
                if _segment_hits_box(dict(zip(('x','y'),a)), dict(zip(('x','y'),b)), c['bbox']):
                    issues.append({'code':'WIRE_COMPONENT_CROSSING','wire':wire['id'],'component':c['designator']})
    for i, (net, a, b) in enumerate(edges):
        for other, c, d in edges[i+1:]:
            if net == other:
                continue
            intersects = any(on_segment(p,a,b) for p in (c,d)) or any(on_segment(p,c,d) for p in (a,b))
            if a[0] == b[0] and c[1] == d[1]:
                intersects |= on_segment((a[0],c[1]),a,b) and on_segment((a[0],c[1]),c,d)
            elif a[1] == b[1] and c[0] == d[0]:
                intersects |= on_segment((c[0],a[1]),a,b) and on_segment((c[0],a[1]),c,d)
            if intersects:
                issues.append({'code':'WIRE_WIRE_CROSSING','nets':[net,other],'segments':[a,b,c,d]})
    covered = []
    for ref, p in pins.items():
        connected = any(net == pin_net[ref] and on_segment(p,a,b) for net,a,b in edges)
        touching = any(other != ref and q == p and pin_net[other] == pin_net[ref] for other,q in pins.items())
        if connected or touching:
            covered.append(ref)
        else:
            issues.append({'code':'ENDPOINT_NOT_VISIBLE','endpoint':ref})
    for m in markers:
        if m['net'].startswith('N_AUTO_'):
            issues.append({'code':'ANONYMOUS_MARKER_VISIBLE','id':m['id']})
        for c in state['components']:
            if _intersects(m['bbox'],c['bbox']):
                issues.append({'code':'MARKER_COMPONENT_OVERLAP','marker':m['id'],'component':c['designator']})
    groups = {}
    for n in nets:
        name = n['name']
        nodes = {p for net,a,b in edges if net == name for p in (a,b)} | {p for ref,p in pins.items() if pin_net[ref] == name}
        nodes |= {point(m) for m in markers if m['net'] == name}
        adjacency = {p:set() for p in nodes}
        for net,a,b in edges:
            if net != name:
                continue
            path = sorted(p for p in nodes if on_segment(p,a,b))
            for left,right in zip(path,path[1:]):
                adjacency[left].add(right); adjacency[right].add(left)
        components = []
        unseen = set(nodes)
        while unseen:
            todo = [next(iter(unseen))]; reached = set()
            while todo:
                p = todo.pop()
                if p in reached:
                    continue
                reached.add(p); todo.extend(adjacency[p] - reached)
            unseen -= reached; components.append(reached)
        groups[name] = len(components)
        if n.get('net_origin') == 'generated' and len(components) != 1:
            issues.append({'code':'ANONYMOUS_DISCONNECTED','net':name})
        if len(components) > 1:
            for group in components:
                if not any(m['net']==name and point(m) in group for m in markers):
                    issues.append({'code':'NAMED_GROUP_WITHOUT_MARKER','net':name})
    return {'ok':not issues,'visible_endpoint_count':len(covered),'expected_endpoint_count':len(pins),'continuous_groups_by_net':groups,'issues':issues}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--export', action='store_true')
    mode.add_argument('--record-reopen', action='store_true', help='Compare the imported copy with the source readback and record validation')
    args = parser.parse_args()
    spec,expanded,resolver,errors,warnings = process(SPEC)
    assert not errors, errors
    components,nets = build_flat(expanded,resolver)
    client = BridgeClient(timeout=35); window = client.health()['active_window_id']
    state,_,error = _state(client,window); assert not error,error
    assert state['source']['page_uuid']=='8a99692c56d721d3'
    topology = verify_schematic_topology(client,SPEC.read_text(),window,str(DESIGN))
    drc = get_schematic_violations(client,window)
    visual = geometry(state,nets)
    annotation_response = client.execute("return (await eda.sch_PrimitiveText.getAll()).map(t=>({id:t.getState_PrimitiveId(),content:t.getState_Content(),x:t.getState_X(),y:t.getState_Y(),font_size:t.getState_FontSize()}));",window)
    assert annotation_response['ok'], annotation_response
    annotations = annotation_response['result']
    assert len(annotations) == 14 and all(t['font_size'] == 6 for t in annotations), annotations
    report = {'format':'amplifier-verification/v0.2','source':state['source'],'revision':state['revision'],'core_errors':errors,'core_warnings':warnings,'topology':topology,'strict_drc':drc,'geometry':visual,'wire_count':len(state['wires']),'net_port_count':len(state['ports']),'ground_flag_count':len(state['flags']),'reopen_verified':False}
    report['value_annotations'] = annotations
    assert topology['ok'] and drc['passed'] and visual['ok'], report
    if args.record_reopen:
        source_state = json.loads((DESIGN/'easyeda/native-readback.json').read_text())
        source_report = json.loads((DESIGN/'easyeda/verification.json').read_text())
        assert state['source']['project_uuid'] != source_state['source']['project_uuid'], 'Reopen verification requires an independently imported project'
        for key in ('components', 'wires', 'ports', 'flags', 'labels', 'no_connects'):
            assert state[key] == source_state[key], f'Reopened {key} differ from source'
        assert annotations == source_report['value_annotations'], 'Reopened annotations differ from source'
        archive = DESIGN/'easyeda/S8050-S8550-Audio-Amplifier.epro2'
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == source_report['archive_sha256']
        report['reopen_verified'] = True
        source_report['reopen_verified'] = True
        source_report['reopen_evidence'] = report
        (DESIGN/'easyeda/verification.json').write_text(json.dumps(source_report,ensure_ascii=False,indent=2)+'\n')
    if args.export:
        state,_,error = _state(client,window); assert not error,error
        assert state['source']['project_uuid']=='b86670ccc7f1377832ce3be0dae93ddeebe7375f9a03ddf53c5983a6aa831dca', 'Export must target the source project, not a reopen copy'
        saved = save_schematic(client,window,state['context_revision'],state['revision']); assert saved['ok'],saved
        response = client.execute("const f=await eda.sys_FileManager.getProjectFile('S8050-S8550-Audio-Amplifier',undefined,'epro2');if(!f)throw Error('No project file');const a=new Uint8Array(await f.arrayBuffer());let s='';for(let i=0;i<a.length;i++)s+=String.fromCharCode(a[i]);return {name:f.name,base64:btoa(s)};",window)
        assert response['ok'],response
        data = base64.b64decode(response['result']['base64'])
        archive = DESIGN/'easyeda/S8050-S8550-Audio-Amplifier.epro2'
        archive.write_bytes(data)
        with zipfile.ZipFile(archive) as package:
            assert package.testzip() is None
            report['zip_members'] = package.namelist()
        report.update({'archive_sha256':hashlib.sha256(data).hexdigest(),'zip_integrity':True,'saved':True})
        for suffix,renderer in [('bom.csv',render_bom_csv),('net',render_protel2_netlist),('mmd',render_mermaid)]:
            name = 'S8050_S8550_Audio_Amplifier'+('-' if suffix=='bom.csv' else '.')+suffix
            (DESIGN/'generated'/name).write_text(renderer(expanded,resolver))
        (DESIGN/'easyeda/native-readback.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
        (DESIGN/'easyeda/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
