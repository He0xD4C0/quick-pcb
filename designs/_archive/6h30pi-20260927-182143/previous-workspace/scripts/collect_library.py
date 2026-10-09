#!/usr/bin/env python3
"""Read-only official EasyEDA library evidence; no guessed UUID or pin maps."""
from pathlib import Path
import sys,json,base64,zipfile,io,collections
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]/'mcp-server'))
from boardspec_mcp.bridge_client import BridgeClient
b=BridgeClient(timeout=90);w='28afe000-45ed-4c84-af2a-71c16dd631b1';out=ROOT/'results/library';out.mkdir(exist_ok=True)
def read(n):return json.loads((out/n).read_text())['result']
a={r['query']:r['items'] for r in read('search-active.json')['rows']};p={r['query']:r['items'] for r in read('search-passive.json')};s={r['query']:r['items'] for r in read('search-symbols.json')};e={r['query']:r['items'] for r in read('search-exact.json')}
selected={}
for key,q,name in [('R','Resistor','电阻_Resistor'),('C','Capacitor','电容_Capacitor'),('CP','Capacitor','CAPACITOR_THT:CP_RADIAL_D8.0MM_P2.50MM'),('F','Fuse','FUSE'),('NET','Netport-BI','Netport-BI')]:
 selected[key]={'kind':'symbol','item':next(x for x in s[q] if x['name']==name)}
for key,item in [('NPN',a['MPSA42'][1]),('MOS',a['IRF820'][0]),('LDO',e['LM1084IT-ADJ/NOPB'][0]),('UF4007',a['UF4007'][0]),('MBR1045',a['MBR1045'][0]),('1N4148',e['1N4148TA'][0]),('1N4007',a['1N4007'][1]),('1N5404',a['1N5404'][1]),('12V zener',p['1N4742A'][0]),('24V zener',p['1N4749A'][1]),('5.1V zener',e['BZX55C5V1'][0])]:selected[key]={'kind':'device','item':item}
for key,z in selected.items():
 item=z['item'];lib=item['libraryUuid'];sym=item['uuid'] if z['kind']=='symbol' else item['symbolUuid']
 code='const f=await eda.sys_FileManager.getSymbolFileBySymbolUuid('+json.dumps(sym)+','+json.dumps(lib)+",'elibz2');if(!f)throw Error('no symbol');const a=new Uint8Array(await f.arrayBuffer());let s='';for(let i=0;i<a.length;i+=8192)s+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(s);"
 r=b.execute(code,w);assert r.get('ok') and isinstance(r.get('result'),str),(key,r)
 archive=base64.b64decode(r['result']);(out/(key.replace(' ','_')+'.elibz2')).write_bytes(archive)
 with zipfile.ZipFile(io.BytesIO(archive)) as zz:
  src='|\n'.join(zz.read(n).decode() for n in zz.namelist() if n.endswith('.elibu'))
 (out/(key.replace(' ','_')+'.elibu')).write_text(src)
 attrs=collections.defaultdict(dict);pins=[]
 for row in src.splitlines():
  if '||' not in row:continue
  row=row.rstrip('|')
  if '||' not in row:continue
  h,v=map(json.loads,row.split('||',1))
  if h['type']=='ATTR':attrs[v['parentId']][v['key']]=v['value']
  elif h['type']=='PIN':pins.append((h['id'],v))
 z['pins']=[dict(number=attrs[i].get('Pin Number'),name=attrs[i].get('Pin Name'),type=attrs[i].get('Pin Type'),x=v.get('x'),y=v.get('y'),rotation=v.get('rotation'),part=v.get('partId')) for i,v in pins]
 print(key,item['name'],z['pins'],flush=True)
 (out/'selected.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
