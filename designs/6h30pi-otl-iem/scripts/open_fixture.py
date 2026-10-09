#!/usr/bin/env python3
import argparse,json
from eda_session import *
p=argparse.ArgumentParser();p.add_argument('name');a=p.parse_args();b,w=session();q=b.execute('return await eda.dmt_Project.getCurrentProjectInfo();',w);(R/'evidence/eda'/(a.name+'-tree.json')).write_text(json.dumps(q,indent=2));ss=[s for s in q['result']['data'] if s.get('name')==a.name];assert len(ss)==1,ss
page=ss[0]['page'][0]['uuid'];r=checked('if(!(await eda.sch_Document.save()))throw Error("save failed");return await eda.dmt_EditorControl.openDocument('+json.dumps(page)+');',a.name+'-open.json');print(page,r.get('ok'))
