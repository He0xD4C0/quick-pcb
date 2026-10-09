#!/usr/bin/env python3
"""Clean redundant net-name attributes in the native page, retaining all actual IDs.
Uses documented setDocumentSource on the authorized task page; no library remapping.
"""
import json,base64,sqlite3
from collections import defaultdict
from eda_session import R,session,checked,_state
from capture_parts import parse
b,w=session();s,_,e=_state(b,w);assert not e
assert s['source']['schematic_name']=='6H30Pi-Stereo-CANDIDATE'
q=b.execute('return await eda.sys_FileManager.getDocumentSource();',w);assert q.get('ok')
(R/'evidence/eda/candidate-before-source-cleanup.json').write_text(json.dumps(q,indent=2))
# Recoverable native checkpoint before the page replacement.
a=sqlite3.connect('file:/Users/he0xd4c0/Documents/LCEDA-Pro/projects/6H30Pi-Rebuild.eprj2?mode=ro',uri=True);d=sqlite3.connect(R/'evidence/eda/candidate-before-source-cleanup.eprj2');a.backup(d);assert d.execute('pragma integrity_check').fetchone()[0]=='ok';a.close();d.close()
doc=next(iter(parse(q['result']).values()));rows=list(doc['rows'].values());markers=s['ports']+s['flags'];nets={m['net'] for m in markers};ids={m['id'] for m in markers};seen=set();out=[];removed=0
B=json.loads((R/'topology-candidate.json').read_text());notes={(n['x'],n['y']):n['text'] for n in B['notes']}
for h,v in rows:
 if h['type']=='ATTR' and v.get('key')=='NET':
  if v.get('value') in nets or v['parentId'] in seen:removed+=1;continue
  seen.add(v['parentId']);v.update(fontSize=11,valueVisible=True,keyVisible=False,rotation=0)
 if h['type']=='ATTR' and v.get('fontSize') is not None and v['fontSize']>100:v['fontSize']=11
 if h['type']=='ATTR' and v.get('parentId') in ids and v.get('key')=='Name':v.update(valueVisible=True,keyVisible=False,fontSize=12)
 if h['type']=='TEXT' and (v.get('x'),v.get('y')) in notes:v['value']=notes[(v['x'],v['y'])]
 # Keep proposed working-point note explicit but use this run's model values.
 if h['type']=='TEXT' and str(v.get('value','')).startswith('TP '):v['value']=v['value'].replace('~80V','82.0V').replace('~2.4V','2.48V').replace('target Iq~35mA (verify)','model Iq=36.51mA; Pa=2.67/2.90W')
 out.append((h,v))
text='|\n'.join(json.dumps(h,separators=(',',':'))+'||'+json.dumps(v,separators=(',',':'),ensure_ascii=False) for h,v in [({'type':'DOCHEAD'},doc['head']),*out])
(R/'evidence/eda/candidate-cleaned-page.epru').write_text(text)
encoded=base64.b64encode(text.encode()).decode()
code='const bytes=Uint8Array.from(atob('+json.dumps(encoded)+'),c=>c.charCodeAt(0));return {setSource:await eda.sys_FileManager.setDocumentSource(new TextDecoder().decode(bytes))};'
r=checked(code,'candidate-set-source-result.json');print('removed redundant NET attrs',removed);print({k:r.get(k) for k in ['ok','code','results']});assert r.get('ok'),r
