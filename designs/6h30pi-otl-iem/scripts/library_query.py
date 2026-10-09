#!/usr/bin/env python3
"""Read-only EasyEDA searches, preserving complete raw results and source window."""
from pathlib import Path
import sys,json,datetime,argparse
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1];sys.path.insert(0,str(REPO/'mcp-server'))
from boardspec_mcp.bridge_client import BridgeClient
p=argparse.ArgumentParser();p.add_argument('queries',nargs='+');p.add_argument('--limit',type=int,default=30);p.add_argument('--out',required=True);p.add_argument('--window-id');args=p.parse_args()
b=BridgeClient(timeout=60);ws=b.list_windows();windows=ws.get('windows',[])
if not windows:raise SystemExit('EDA Bridge has no connected EDA window')
w=args.window_id or next((v for v in windows if v.get('active')),windows[0])['id'];assert any(v['id']==w for v in windows),'requested window disconnected';rows=[]
for q in args.queries:
 r=b.execute('return await eda.lib_Device.search('+json.dumps(q)+',undefined,undefined,undefined,'+str(args.limit)+',1);',w)
 if not r.get('ok'):raise RuntimeError((q,r))
 rows.append({'query':q,'items':r.get('result') or []});print(q,len(rows[-1]['items']),flush=True)
 (ROOT/'evidence/library'/args.out).write_text(json.dumps({'captured_at':datetime.datetime.now().astimezone().isoformat(),'window_id':w,'rows':rows},ensure_ascii=False,indent=2)+'\n')
