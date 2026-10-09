#!/usr/bin/env python3
import json,base64,hashlib
from eda_session import R,session,checked,_state
from capture_parts import parse
b,w=session();s,_,e=_state(b,w);assert not e
q=b.execute('return await eda.sys_FileManager.getDocumentSource();',w);assert q.get('ok');doc=next(iter(parse(q['result']).values()));rows=list(doc['rows'].values());B=json.loads((R/'topology-candidate.json').read_text());P={p['ref']:p for p in B['parts']};L=json.loads((R/'parts.lock.json').read_text())['parts'];A=json.loads((R/'parts.audit.json').read_text())['reviews'];components={c['id']:c for c in s['components']};markerids={p['id'] for p in s['ports']+s['flags']}
for h,v in rows:
 if h['type'] in ['TEXT','ATTR']:
  v['fontFamily']='Arial'
 if h['type']=='ATTR' and v.get('parentId') in markerids and v.get('key')=='Name':v.update(fontSize=12,valueVisible=True,keyVisible=False)
 if h['type']=='ATTR' and v.get('parentId') in components and v.get('key')=='Name':
  c=components[v['parentId']];key=P[c['designator']]['key']
  if key.startswith(('r_','c_')):v['valueVisible']=False
 if h['type']=='TEXT' and str(v.get('value','')).startswith('TP '):
  v['value']='MODEL: VMID=82.0V, VK=2.48V, Iq=36.51mA';v['y']=900
 if h['type']=='TEXT' and str(v.get('value','')).startswith('RS 127R'):
  v['value']='Pa upper/lower=2.67/2.90W. CO1000u/250V, + toward tube';v['y']=940
 # Offset section headers from the power marker above the incoming rail.
 if h['type']=='TEXT' and v.get('value') in ['02 LEFT / PURE TUBE WCF','03 RIGHT / PURE TUBE WCF']:v['y']=150
new=[]
for c in s['components']:
 key=P[c['designator']]['key']
 if not key.startswith(('r_','c_')):continue
 z=L[key];rating=A[key]['ratings'];value=z['library_properties']['Value']
 if key.startswith('r_'):value+=' / '+str(rating['power_W_at_70C'])+'W'
 else:value+=' / '+str(rating['rated_V'])+'V'
 id=hashlib.sha256(('candidate-display-value:'+c['id']).encode()).hexdigest()[:16]
 v={'groupId':'','locked':False,'zIndex':3,'x':c['x']/10+30,'y':-c['y']/10-15,'rotation':0,'color':None,'fillColor':None,'fontFamily':'Arial','fontSize':11,'strikeout':False,'underline':False,'italic':False,'fontWeight':None,'align':'LEFT_BOTTOM','version':'2.0','value':value}
 new.append(({'type':'TEXT','id':id,'ticket':0},v))
ids={h['id'] for h,v in new};rows=[(h,v) for h,v in rows if h['id'] not in ids];ticket=max(h.get('ticket',0) for h,v in rows)
for i,(h,v) in enumerate(new):h['ticket']=ticket+i+1
rows.extend(new)
text='|\n'.join(json.dumps(h,separators=(',',':'))+'||'+json.dumps(v,separators=(',',':'),ensure_ascii=False) for h,v in [({'type':'DOCHEAD'},doc['head']),*rows]);(R/'evidence/eda/candidate-final-page.epru').write_text(text)
encoded=base64.b64encode(text.encode()).decode();r=checked('const a=Uint8Array.from(atob('+json.dumps(encoded)+'),c=>c.charCodeAt(0));return {setSource:await eda.sys_FileManager.setDocumentSource(new TextDecoder().decode(a))};','candidate-add-ratings.json');assert r.get('ok'),r;print('rating captions',len(new))
