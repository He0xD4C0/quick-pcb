#!/usr/bin/env python3
import json,base64
from eda_session import R,session,checked
from capture_parts import parse
b,w=session();q=b.execute('return await eda.sys_FileManager.getDocumentSource();',w);assert q.get('ok');d=next(iter(parse(q['result']).values()));rows=list(d['rows'].values())
ports={'7db0574a01200846':(615,275,'RIGHT_MIDDLE'),'c699f250f399a6f2':(665,275,'LEFT_MIDDLE')}
lineids={'2e2a734ad0beb35d','bed6423597886daa','e1bc99203017fe6a'}
for h,v in rows:
 if h['type']=='COMPONENT' and h['id'] in ports:v['rotation']=90
 if h['type']=='ATTR' and v.get('parentId') in ports and v.get('key')=='Name':v['x'],v['y'],v['align']=ports[v['parentId']];v['rotation']=0
 if h['type']=='LINE' and h['id'] in lineids:
  for f in ['startY','endY']:
   if v[f]==290:v[f]=240
 if h['type']=='TEXT' and v.get('value')=='8.2kΩ / 0.25W' and v.get('y')==245:v['x']=380
 if h['type']=='ATTR' and v.get('key')=='NET' and v.get('value')=='SEL_R':v.update(x=760,y=400,rotation=0,align='LEFT_BOTTOM')
source='|\n'.join(json.dumps(h,separators=(',',':'))+'||'+json.dumps(v,separators=(',',':'),ensure_ascii=False) for h,v in [({'type':'DOCHEAD'},d['head']),*rows]);encoded=base64.b64encode(source.encode()).decode()
r=checked('const a=Uint8Array.from(atob('+json.dumps(encoded)+'),c=>c.charCodeAt(0));return {setSource:await eda.sys_FileManager.setDocumentSource(new TextDecoder().decode(a))};','candidate-finish-readability.json');assert r.get('ok'),r
