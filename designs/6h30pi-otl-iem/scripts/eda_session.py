"""Resolve the one authorized rebuild project; never use an unrelated active window."""
import sys,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parents[1]/'mcp-server'))
from boardspec_mcp.bridge_client import BridgeClient
from boardspec_mcp.schematic_tools import _state,_checked_write
PROJECT='7d97ffb2c360e04d46022ccf3f71a672eaf146094459f74aed083c5ed86ef406'
def session():
 b=BridgeClient(timeout=45)
 found=[]
 for w in b.list_windows().get('windows',[]):
  q=b.execute('return await eda.dmt_Project.getCurrentProjectInfo();',w['id'])
  if q.get('ok') and isinstance(q.get('result'),dict) and q['result'].get('uuid')==PROJECT:found.append(w['id'])
 assert len(found)==1,('Need exactly one rebuild window',found)
 return b,found[0]
def checked(program,evidence):
 b,w=session();s,_,e=_state(b,w);assert not e,e;assert s['source']['project_uuid']==PROJECT
 q=_checked_write(b,w,s['context_revision'],s['revision'],program)
 (R/'evidence/eda'/evidence).write_text(json.dumps({'before':s,'result':q},indent=2)+'\n');return q
