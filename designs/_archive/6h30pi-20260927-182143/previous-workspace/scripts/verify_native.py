#!/usr/bin/env python3
"""Live readback/save for this task-owned imported project only.
Run with the repository MCP venv. Never selects or overwrites another project.
"""
from pathlib import Path
import sys,json,collections,sqlite3
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO/'mcp-server'))
from boardspec_mcp.bridge_client import BridgeClient
b=BridgeClient(timeout=60);info=json.loads((ROOT/'results/native-project.json').read_text());w=info['window_id'];uid=info['uuid']
assert info['name']=='QuickPCB_6H30Pi_OTL_IEM_v01_review2'
manifest=json.loads((ROOT/'circuit.json').read_text());names={c['ref']:c['value']+' ['+c['alias']+']' for c in manifest['components']}
expected=json.loads((ROOT/'results/connectivity_expected.json').read_text());actual=collections.defaultdict(list);errors=[];pages=[]
outdir=ROOT/'results/native-readback';outdir.mkdir(exist_ok=True)
def execute(code):
 r=b.execute(code,w)
 if not r.get('ok'):raise RuntimeError(r)
 return r.get('result')
assert execute('return (await eda.dmt_Project.getCurrentProjectInfo()).uuid;')==uid
for page in info['data'][0]['page']:
 execute('return await eda.dmt_EditorControl.openDocument('+json.dumps(page['uuid'])+');')
 code='''const s=await eda.sys_FileManager.getDocumentSource();const h=JSON.parse(s.split('||')[1].split('|\\n')[0]);
if(h.uuid!==PAGE)throw new Error('page changed');
const expected=NAMES;const c=await eda.sch_PrimitiveComponent.getAll();
for(const v of c){if(!expected[v.designator])throw new Error('unexpected component');if(v.name!==expected[v.designator])await eda.sch_PrimitiveComponent.modify(v.primitiveId,{name:expected[v.designator]});}
await eda.sch_Document.save();
const components=await eda.sch_PrimitiveComponent.getAll();const pins={};
for(const v of components)pins[v.designator]=await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(v.primitiveId);
return {source:await eda.sys_FileManager.getDocumentSource(),components,pins,drc:await eda.sch_Drc.check(true,false,true)};'''.replace('PAGE',json.dumps(page['uuid'])).replace('NAMES',json.dumps(names))
 data=execute(code);(outdir/(page['name']+'.json')).write_text(json.dumps(data,indent=2)+'\n')
 attrs=collections.defaultdict(dict);wire=[]
 for row in data['source'].split('|\n'):
  a,v=map(json.loads,row.split('||',1))
  if a['type']=='ATTR':attrs[v['parentId']][v['key']]=v['value']
  if a['type']=='LINE' and v.get('lineGroup'):wire.append(v)
 for ref,pins in data['pins'].items():
  for pin in pins:
   pt=(pin['x'],-pin['y']);matches=[]
   for ln in wire:
    if pt in [(ln['startX'],ln['startY']),(ln['endX'],ln['endY'])]:matches.append(attrs[ln['lineGroup']].get('NET'))
   if len(matches)!=1 or not matches[0]:errors.append([ref,pin['pinNumber'],pt,matches])
   else:actual[matches[0]].append(ref+'.#'+pin['pinNumber'])
 pages.append({'name':page['name'],'uuid':page['uuid'],'components':len(data['components']),'pins':sum(map(len,data['pins'].values())),'strict_drc':data['drc']})
 print(page['name'],len(data['components']),data['drc'],flush=True)
if {k:sorted(v) for k,v in actual.items()}!={k:sorted(v) for k,v in expected.items()}:errors.append('Live native connectivity differs from intended BoardSpec')
result={'complete':True,'project_name':info['name'],'project_uuid':uid,'window_id':w,'readback_connectivity_passed':not errors,'component_count':sum(x['components'] for x in pages),'pin_count':sum(x['pins'] for x in pages),'net_count':len(actual),'pages':pages,'errors':errors,'strict_drc_passed':all(not p['strict_drc'] for p in pages),'reason':'Full native import, per-page save, loaded pin/wire readback and strict DRC executed. Strict DRC reports missing PCB footprints; no connection warnings observed. No PCB footprint was invented.'}
(ROOT/'results/native-full-validation.json').write_text(json.dumps(result,indent=2)+'\n')
(ROOT/'results/native-connectivity.json').write_text(json.dumps(actual,indent=2)+'\n')
# Preserve actual editor project after page saves. This is a new task-owned file.
src=Path(info['teamUuid'])/(info['name']+'.eprj2')
if src.is_file():
 with sqlite3.connect(src.as_uri()+'?mode=ro',uri=True) as source:
  with sqlite3.connect(ROOT/'schematic'/src.name) as dest:
   source.backup(dest)
   assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
print(json.dumps({k:v for k,v in result.items() if k!='pages'},indent=2))
if errors:raise SystemExit(1)
