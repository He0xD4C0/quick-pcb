#!/usr/bin/env python3
import json,base64,argparse
from eda_session import R,checked,PROJECT
p=argparse.ArgumentParser();p.add_argument('evidence_name');a=p.parse_args()
blob=base64.b64encode((R/'evidence/eda/library-fixture.epro2').read_bytes()).decode()
code='if(!(await eda.sch_Document.save()))throw Error("save failed");const a=Uint8Array.from(atob('+json.dumps(blob)+'),c=>c.charCodeAt(0));const f=new File([a],"library-fixture.epro2");return await eda.sys_FileManager.importProjectByProjectFile(f,"JLCEDA Pro",{importOption:"ImportDocument",associateFootprint:true},{operation:"Existing Project",existingProjectUuid:'+json.dumps(PROJECT)+'});'
r=checked(code,a.evidence_name+'.json');print(json.dumps({k:r.get(k) for k in ['ok','code','results','revision_before','revision_after']}))
