#!/usr/bin/env python3
"""Use native attribute edits for readable NET labels; preserve original library values."""
import json
from collections import defaultdict
from eda_session import R,session,checked,_state
from capture_parts import parse
b,w=session();s,_,e=_state(b,w);assert not e,e
q=b.execute('return await eda.sys_FileManager.getDocumentSource();',w);assert q.get('ok')
(R/'evidence/eda/candidate-before-polish-source.json').write_text(json.dumps(q,indent=2))
rows=list(next(iter(parse(q['result']).values()))['rows'].values())
ports={p['id']:p for p in s['ports']+s['flags']};nets_with_markers={p['net'] for p in ports.values()}
wireattrs=defaultdict(list);edits=[]
for h,v in rows:
 if h['type']=='ATTR' and v.get('key')=='NET':wireattrs[v['parentId']].append((h,v))
for parent,attrs in wireattrs.items():
 for j,(h,v) in enumerate(attrs):
  if v['value'] in nets_with_markers or j>0:edits.append({'id':h['id'],'props':{'key':'RoutingAlias','valueVisible':False,'keyVisible':False}})
  else:edits.append({'id':h['id'],'props':{'valueVisible':True,'keyVisible':False,'fontSize':11,'rotation':0}})
# True NET port Name attributes were hidden by SDK defaults. Make them visible.
for h,v in rows:
 if h['type']=='ATTR' and v.get('parentId') in ports and v.get('key')=='Name':
  edits.append({'id':h['id'],'props':{'valueVisible':True,'keyVisible':False,'fontSize':12}})
# Restore factory Name formulas; ratings are already documented in block notes / BOM.
L=json.loads((R/'parts.lock.json').read_text())['parts'];B=json.loads((R/'topology-candidate.json').read_text());byref={p['ref']:p for p in B['parts']};cs={c['id']:c for c in s['components']}
for h,v in rows:
 if h['type']!='ATTR' or v.get('parentId') not in cs:continue
 c=cs[v['parentId']];p=byref[c['designator']];key=p['key']
 if key in L and v.get('key')=='Name':edits.append({'id':h['id'],'props':{'value':L[key]['library_properties']['Name'],'valueVisible':True}})
 # Place custom captions above the symbol body rather than over contacts/pins.
 if key not in L and v.get('key') in ['Name','Designator']:
  y=c['y']/10+(100 if key!='tube_6h30pi_eb' else 105)
  edits.append({'id':h['id'],'props':{'x':c['x']/10-40,'y':y+(15 if v['key']=='Designator' else 0)}})
for at in range(0,len(edits),120):
 batch=edits[at:at+120]
 r=checked('const out=[];for(const e of '+json.dumps(batch)+'){const a=await eda.sch_PrimitiveAttribute.modify(e.id,e.props);if(!a)throw Error("attribute edit failed: "+e.id);out.push(a.getState_PrimitiveId());}return out;','candidate-polish-'+str(at)+'.json');assert r.get('ok'),r
 print('attributes',at+len(batch),flush=True)
