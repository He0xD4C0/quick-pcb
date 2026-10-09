#!/usr/bin/env python3
"""Save/reopen/export the actual one-sheet EasyEDA project and verify persistence."""
import json,base64,sqlite3,hashlib,datetime
from collections import Counter
from eda_session import R,session,checked,_state,PROJECT
from boardspec_mcp.schematic_tools import get_schematic_violations
O=R/'delivery';O.mkdir(exist_ok=True);b,w=session();before,_,e=_state(b,w);assert not e
assert before['source']['schematic_name']=='6H30Pi-Stereo-CANDIDATE'
tree=b.execute('return await eda.dmt_Project.getCurrentProjectInfo();',w)['result'];schematics=[x for x in tree['data'] if x.get('page')];assert len(schematics)==1 and len(schematics[0]['page'])==1,schematics
r=checked('return {saved:await eda.sch_Document.save()};','candidate-final-save.json');assert r.get('ok') and r['results'][0]['saved'],r
page=before['source']['page_uuid'];tab=before['source']['tab_id']
r=b.execute('if((await eda.dmt_Project.getCurrentProjectInfo())?.uuid!=='+json.dumps(PROJECT)+')throw Error("project changed");if(!(await eda.dmt_EditorControl.closeDocument('+json.dumps(tab)+')))throw Error("close failed");return await eda.dmt_EditorControl.openDocument('+json.dumps(page)+');',w);assert r.get('ok'),r
after,_,e=_state(b,w);assert not e,e
identity=lambda s:sorted((c['designator'],c['sub_part_name'],tuple((p['number'],round(p['x'],6),round(p['y'],6)) for p in c['pins'])) for c in s['components'])
assert identity(before)==identity(after),'pins changed on reopen'
assert before['no_connects']==after['no_connects']
assert len(before['ports'])==len(after['ports']) and len(before['flags'])==len(after['flags'])
(R/'evidence/eda/candidate-final-state.json').write_text(json.dumps(after,indent=2)+'\n')
source=b.execute('return await eda.sys_FileManager.getDocumentSource();',w);assert source.get('ok');(R/'evidence/eda/candidate-final-source.json').write_text(json.dumps(source,indent=2)+'\n')
for ext,expr in [('epro2','eda.sys_FileManager.getProjectFile("6H30Pi-Stereo-CANDIDATE",undefined,"epro2")'),('png','eda.sch_ManufactureData.getExportDocumentFile("6H30Pi-Stereo-CANDIDATE","PNG",{size:"Original Size"},"Current Schematic Page")')]:
 q=b.execute('const f=await '+expr+';if(!f)throw Error("export failed");const a=new Uint8Array(await f.arrayBuffer());let t="";for(let i=0;i<a.length;i+=8192)t+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(t);',w);assert q.get('ok') and isinstance(q.get('result'),str),q;(O/('6H30Pi-Stereo-CANDIDATE.'+ext)).write_bytes(base64.b64decode(q['result']))
src='/Users/he0xd4c0/Documents/LCEDA-Pro/projects/6H30Pi-Rebuild.eprj2';dst=O/'6H30Pi-Stereo-CANDIDATE.eprj2';a=sqlite3.connect('file:'+src+'?mode=ro',uri=True);d=sqlite3.connect(dst);a.backup(d);integrity=d.execute('pragma integrity_check').fetchone()[0];a.close();d.close();assert integrity=='ok'
drc=get_schematic_violations(b,w);assert drc.get('ok');(O/'native-drc.json').write_text(json.dumps(drc,indent=2)+'\n')
report={'captured_at':datetime.datetime.now().astimezone().isoformat(),'kind':'COMPLETE_DRAWING_CANDIDATE_NOT_QUALIFIED_HARDWARE','project_uuid':PROJECT,'page_uuid':page,'live_native_path':src,'schematics':1,'pages':1,'physical_components':len({c['designator'] for c in after['components']}),'drawn_component_units':len(after['components']),'ports':len(after['ports']),'flags':len(after['flags']),'wire_groups':len(after['wires']),'no_connects':len(after['no_connects']),'saved_reopened_pin_identity_equal':True,'coordinate_comparison_tolerance_mil':0.000001,'sqlite_integrity':integrity,'native_drc':dict(Counter(r['severity'] for r in drc['violations'])),'native_netlist_available':bool(after.get('netlist')),'simulation_acceptance':'NOT_PASSED','physical_test':'NOT_PERFORMED','Codex_restarted':False}
(O/'checkpoint.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
