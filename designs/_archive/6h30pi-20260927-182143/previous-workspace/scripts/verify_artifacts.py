#!/usr/bin/env python3
"""Independent reconstruction of native-file pin -> wire NET connectivity.
This is a STATIC artifact check, not an EasyEDA application DRC replacement.
"""
from pathlib import Path
import json,collections,math,zipfile
ROOT=Path(__file__).resolve().parents[1]

def main():
 data=json.loads((ROOT/'circuit.json').read_text());expected=json.loads((ROOT/'results/connectivity_expected.json').read_text())
 records=[];doc=None;docs=[]
 for row in (ROOT/'schematic/6H30Pi-OTL.epru').read_text().split('|\n'):
  a,b=map(json.loads,row.split('||',1))
  if a['type']=='DOCHEAD':doc={'head':b,'records':[]};docs.append(doc)
  else:doc['records'].append((a,b))
 symbols={}
 for d in docs:
  if d['head']['docType']!='SYMBOL':continue
  attrs=collections.defaultdict(dict)
  for a,b in d['records']:
   if a['type']=='ATTR':attrs[b['parentId']][b['key']]=b['value']
  symbols[d['head']['uuid']]={attrs[a['id']]['Pin Number']:(b['x'],b['y']) for a,b in d['records'] if a['type']=='PIN'}
 actual=collections.defaultdict(list);count=0;errors=[];native_refs=set()
 for d in docs:
  if d['head']['docType']!='SCH_PAGE':continue
  attrs=collections.defaultdict(dict);wires={}
  for a,b in d['records']:
   if a['type']=='ATTR':attrs[b['parentId']][b['key']]=b['value']
   if a['type']=='LINE' and b.get('lineGroup'):wires[b['lineGroup']]=b
  for a,b in d['records']:
   if a['type']!='COMPONENT':continue
   props=attrs[a['id']];ref=props['Designator'];native_refs.add(ref);count+=1
   for pin,(dx,dy) in symbols[props['Symbol']].items():
    pt=(b['x']+dx,b['y']+dy);matches=[]
    for wid,w in wires.items():
     if pt in [(w['startX'],w['startY']),(w['endX'],w['endY'])]:matches.append(attrs[wid].get('NET'))
    if len(matches)!=1 or not matches[0]:errors.append(f'{ref}.{pin}: expected exactly one labelled wire, found {matches}')
    else:actual[matches[0]].append(ref+'.#'+pin)
 e={k:sorted(v) for k,v in expected.items()};a={k:sorted(v) for k,v in actual.items()}
 if a!=e:errors.append('Native pin/net memberships differ from BoardSpec manifest')
 if len(native_refs)!=len(data['components']):errors.append('Component ref count mismatch')
 # all endpoints present exactly once, no invented absent refs or unused pins
 total=sum(len(x['pins']) for x in data['components'])
 if sum(map(len,actual.values()))!=total:errors.append('Pin coverage incomplete')
 z=zipfile.ZipFile(ROOT/'schematic/6H30Pi-OTL.epro2');assert z.testzip() is None
 assert z.read('6H30Pi-OTL.epru')==(ROOT/'schematic/6H30Pi-OTL.epru').read_bytes()
 result={'static_ok':not errors,'components':count,'nets':len(actual),'connected_pins':total,'sheets':sum(d['head']['docType']=='SCH_PAGE' for d in docs),'errors':errors,'application_drc':'SEE_NATIVE_FULL_VALIDATION_JSON','note':'No footprints assigned, by design for schematic-only stage; a strict native PCB-conversion rule may report missing footprints. No fake footprint is used to suppress this.'}
 (ROOT/'results/artifact-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
