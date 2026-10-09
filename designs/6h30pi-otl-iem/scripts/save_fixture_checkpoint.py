#!/usr/bin/env python3
"""Save/reopen the actual native fixture and export it as test evidence only."""
import json,base64,sqlite3,hashlib
from pathlib import Path
from collections import Counter
from eda_session import R,session,checked,_state,PROJECT
from boardspec_mcp.schematic_tools import get_schematic_violations
b,w=session();before,_,e=_state(b,w);assert not e,e
assert before['source']['page_uuid']=='f46a303398832651',before['source']
saved=checked('return {saved:await eda.sch_Document.save()};','fixture-final-save.json');assert saved.get('ok') and saved['results'][0]['saved'],saved
# Closing/reopening only this saved task page is authorized by the loading test.
tab=before['source']['tab_id'];page=before['source']['page_uuid']
q=b.execute('if((await eda.dmt_Project.getCurrentProjectInfo())?.uuid!=='+json.dumps(PROJECT)+')throw Error("project changed");if(!(await eda.dmt_EditorControl.closeDocument('+json.dumps(tab)+')))throw Error("close failed");return await eda.dmt_EditorControl.openDocument('+json.dumps(page)+');',w)
assert q.get('ok'),q
after,_,e=_state(b,w);assert not e,e
identity=lambda s:sorted((c['designator'],c['sub_part_name'],tuple(sorted(p['number'] for p in c['pins']))) for c in s['components'])
assert identity(before)==identity(after),'pins/components changed on reopen'
assert before['no_connects']==after['no_connects'],'No Connect flags changed on reopen'
assert len(after['ports'])==2 and len(after['wires'])==3,('fixture geometry changed',len(after['ports']),len(after['wires']))
(R/'evidence/eda/fixture-reopened-state.json').write_text(json.dumps(after,indent=2)+'\n')
code='const f=await eda.sys_FileManager.getProjectFile("6H30Pi-LIBRARY-TEST-ONLY",undefined,"epro2");if(!f)throw Error("no project export");const a=new Uint8Array(await f.arrayBuffer());let t="";for(let i=0;i<a.length;i+=8192)t+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(t);'
x=b.execute(code,w);assert x.get('ok') and isinstance(x.get('result'),str),x
out=R/'evidence/eda';p=out/'6H30Pi-LIBRARY-TEST-ONLY.epro2';p.write_bytes(base64.b64decode(x['result']))
src=Path('/Users/he0xd4c0/Documents/LCEDA-Pro/projects/6H30Pi-Rebuild.eprj2');dst=out/'6H30Pi-LIBRARY-TEST-ONLY.eprj2'
a=sqlite3.connect('file:'+str(src)+'?mode=ro',uri=True);d=sqlite3.connect(dst);a.backup(d);integrity=d.execute('pragma integrity_check').fetchone()[0];d.close();a.close();assert integrity=='ok'
files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [p,dst]}
drc=get_schematic_violations(b,w);assert drc.get('ok'),drc
(out/'fixture-drc-detailed-after-reopen.json').write_text(json.dumps(drc,indent=2)+'\n')
counts=Counter()
for row in drc['violations']:counts[row['severity']]+=row.get('count',1)
report={'purpose':'LIBRARY TEST ONLY; not the amplifier schematic','project_uuid':PROJECT,'live_native_path':str(src),'page_uuid':page,'saved_reopened_component_pins_equal':True,'native_NET_ports':2,'wires':3,'sqlite_integrity':integrity,'sha256':files,'full_load_gate':'FAILED_NATIVE_NETLIST_AND_DRC','native_drc':dict(counts),'no_connects':len(after['no_connects']),'drc_detail_evidence':'fixture-drc-detailed-after-reopen.json','netlist_comparison':'BLOCKED_MISSING_TUBE_SOCKET_FOOTPRINT','hardware_test':'NOT_PERFORMED'}
(out/'fixture-checkpoint.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
