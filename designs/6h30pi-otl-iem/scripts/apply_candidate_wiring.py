#!/usr/bin/env python3
import json
from eda_session import R,session,checked,_state
from boardspec_mcp.schematic_tools import set_schematic_no_connects
P=json.loads((R/'evidence/eda/candidate-routing-plan.json').read_text())
b,w=session();s,_,e=_state(b,w);assert not e,e
assert s['source']['schematic_name']=='6H30Pi-Stereo-CANDIDATE',s['source']
assert len(s['wires'])==0,'Do not replay writes; inspect current state before resuming'
for at in range(0,len(P['wires']),80):
 batch=P['wires'][at:at+80]
 code='const out=[];for(const t of '+json.dumps(batch)+'){const o=await eda.sch_PrimitiveWire.create(t.points.flat(),t.net);if(!o)throw Error("wire failed");out.push(o.getState_PrimitiveId());}return out;'
 r=checked(code,'candidate-wire-batch-'+str(at)+'.json');assert r.get('ok'),r
 print('wires',at+len(batch),flush=True)
for at in range(0,len(P['markers']),20):
 batch=P['markers'][at:at+20]
 code='const out=[];for(const t of '+json.dumps(batch)+'){const o=t.kind==="flag"?await eda.sch_PrimitiveComponent.createNetFlag(t.identification,t.net,t.x,t.y,0,false):await eda.sch_PrimitiveComponent.createNetPort("BI",t.net,t.x,t.y,t.rotation,false);if(!o)throw Error("marker failed");out.push(o.getState_PrimitiveId());}return out;'
 r=checked(code,'candidate-marker-batch-'+str(at)+'.json');assert r.get('ok'),r
 print('markers',at+len(batch),flush=True)
s,_,e=_state(b,w);assert not e
r=set_schematic_no_connects(b,w,s['context_revision'],s['revision'],[{'designator':'SW1','pin_selectors':['#0']}]);assert r.get('ok'),r
(R/'evidence/eda/candidate-no-connect.json').write_text(json.dumps(r,indent=2))
r=checked('return {saved:await eda.sch_Document.save()};','candidate-wired-save.json');assert r.get('ok'),r
