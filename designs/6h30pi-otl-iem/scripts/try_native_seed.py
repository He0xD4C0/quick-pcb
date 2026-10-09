#!/usr/bin/env python3
"""Create only an empty, uniquely identified import seed using the documented API.
No previous topology is reused. Never overwrite an existing active project.
"""
from pathlib import Path
import sys,json,uuid,zipfile,base64,datetime
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parents[1]/'mcp-server'))
from boardspec_mcp.bridge_client import BridgeClient
b=BridgeClient(timeout=30);w='69fb62cd-2bdb-4a4f-b6cc-2bc96cb91053'
before=b.execute('return {project:await eda.dmt_Project.getCurrentProjectInfo(),document:await eda.dmt_SelectControl.getCurrentDocumentInfo()};',w)
assert before.get('ok') and not before.get('result',{}).get('project'),before
sid,pid=uuid.uuid4().hex,uuid.uuid4().hex
rows=[]
def row(t,i,**v):rows.append(json.dumps({'type':t,**({'id':i,'ticket':len(rows)} if i else {})},separators=(',',':'))+'||'+json.dumps(v,separators=(',',':')))
row('DOCHEAD',None,docType='SCH',uuid=sid,client='qpcb-rebuild',editVersion='3.2.186')
row('META','META',title='6H30Pi-Rebuild',board='')
row('DOCHEAD',None,docType='SCH_PAGE',uuid=pid,client='qpcb-rebuild',editVersion='3.2.186')
row('CANVAS','CANVAS',originX=0,originY=0)
row('META','META',title='OneSheet',schematic=sid,zIndex=1)
row('TEXT','seed-note',value='EMPTY REBUILD SEED / NOT A CIRCUIT',x=100,y=100,fontSize=16,align='LEFT_BOTTOM',rotation=0,zIndex=1,version='2.0')
e=R/'evidence/eda';e.mkdir(exist_ok=True);p=e/'empty-seed.epro2'
with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('project2.json',json.dumps({'title':'6H30Pi-Rebuild','cbb_project':False,'editorVersion':'3.2.186','tags':'[]'}));z.writestr('rebuild.epru','|\n'.join(rows))
code='const a=Uint8Array.from(atob('+json.dumps(base64.b64encode(p.read_bytes()).decode())+'),c=>c.charCodeAt(0));const f=new File([a],"6H30Pi-Rebuild.epro2");return await eda.sys_FileManager.importProjectByProjectFile(f,"JLCEDA Pro",{importOption:"ImportDocument",associateFootprint:true},{operation:"New Project",newProjectOwnerTeamUuid:"/Users/he0xd4c0/Documents/LCEDA-Pro/projects",newProjectName:"6H30Pi-Rebuild",newProjectFriendlyName:"6H30Pi-Rebuild"});'
try:result=b.execute(code,w)
except Exception as exc:result={'transport_exception':str(exc),'write_status':'UNKNOWN_READ_BEFORE_RETRY'}
after=b.execute('return {project:await eda.dmt_Project.getCurrentProjectInfo(),document:await eda.dmt_SelectControl.getCurrentDocumentInfo()};',w)
record={'time':datetime.datetime.now().astimezone().isoformat(),'window_id':w,'before':before,'import_result':result,'after':after,'seed_schematic_uuid':sid,'seed_page_uuid':pid}
(e/'seed-import-result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
