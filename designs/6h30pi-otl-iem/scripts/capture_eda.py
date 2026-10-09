#!/usr/bin/env python3
"""Read native state and a native PNG export; do not redraw a substitute image."""
import json,base64,argparse
from eda_session import R,session,_state
p=argparse.ArgumentParser();p.add_argument('name');a=p.parse_args();b,w=session();s,_,e=_state(b,w);assert not e,e
out=R/'evidence/eda';(out/(a.name+'-state.json')).write_text(json.dumps(s,indent=2)+'\n')
code='const f=await eda.sch_ManufactureData.getExportDocumentFile("readback","PNG",{size:"Original Size"},"Current Schematic Page");if(!f)throw Error("noPNG"); const a=new Uint8Array(await f.arrayBuffer());let t="";for(let i=0;i<a.length;i+=8192)t+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(t);'
x=b.execute(code,w);assert x.get('ok') and isinstance(x.get('result'),str),x;(out/(a.name+'.png')).write_bytes(base64.b64decode(x['result']))
y=b.execute('return await eda.sys_FileManager.getDocumentSource();',w);(out/(a.name+'-source.json')).write_text(json.dumps(y,indent=2)+'\n')
print('components',[(c['designator'],c['sub_part_name'],len(c['pins'])) for c in s['components']]);print(out/(a.name+'.png'))
