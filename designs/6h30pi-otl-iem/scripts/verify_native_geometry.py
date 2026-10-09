#!/usr/bin/env python3
"""Independent connection check of native LINE records and actual EDA pin readback.
Does not bypass/replace native DRC or manufacture-netlist export.
"""
import json,math,argparse
from pathlib import Path
from collections import defaultdict
from capture_parts import parse
R=Path(__file__).resolve().parents[1];O=R/'evidence/eda'
ap=argparse.ArgumentParser();ap.add_argument('name',default='candidate-polished',nargs='?');args=ap.parse_args()
S=json.loads((O/(args.name+'-state.json')).read_text());source=json.loads((O/(args.name+'-source.json')).read_text())['result'];rows=list(next(iter(parse(source).values()))['rows'].values())
B=json.loads((R/'topology-candidate.json').read_text());parent={};wirepoints=defaultdict(set)
def root(x):
 parent.setdefault(x,x)
 if parent[x]!=x:parent[x]=root(parent[x])
 return parent[x]
def union(a,b):parent[root(a)]=root(b)
def pt(x,y):return round(x,6),round(y,6)
segments=[]
for h,v in rows:
 if h['type']!='LINE':continue
 a=pt(v['startX'],v['startY']);b=pt(v['endX'],v['endY']);assert a[0]==b[0] or a[1]==b[1]
 # Actual geometry grid is 5 source units, but use 1 to include every integer endpoint.
 n=round(max(abs(a[0]-b[0]),abs(a[1]-b[1])));points=[pt(a[0]+(b[0]-a[0])*i/max(n,1),a[1]+(b[1]-a[1])*i/max(n,1)) for i in range(n+1)]
 for p in points:union(a,p)
 wirepoints[v['lineGroup']].update(points);segments.append((a,b))
names=defaultdict(set)
for h,v in rows:
 if h['type']=='ATTR' and v.get('key')=='NET' and v.get('value'):
  for p in wirepoints.get(v['parentId'],[]):names[root(p)].add(v['value'])
for p in S['ports']+S['flags']:
 loc=pt(p['x']/10,-p['y']/10);names[root(loc)].add(p['net'])
expected={net:set(ends) for net,ends in B['nets'].items()};actual=defaultdict(set);unattached=[];shorts=[];pinrows=[]
for c in S['components']:
 for p in c['pins']:
  key=c['designator']+'.#'+p['number'];loc=pt(p['x']/10,-p['y']/10);r=root(loc);ns=names[r]
  pinrows.append({'endpoint':key,'point':loc,'native_geometry_net_names':sorted(ns),'no_connect':p['no_connected']})
  if not ns:
   if not p['no_connected']:unattached.append(key)
  elif len(ns)>1:shorts.append({'pin':key,'names':sorted(ns)})
  else:actual[next(iter(ns))].add(key)
missing={n:sorted(v-actual[n]) for n,v in expected.items() if v-actual[n]};extra={n:sorted(v-expected.get(n,set())) for n,v in actual.items() if v-expected.get(n,set())}
report={'kind':'native-geometry-and-pin-readback; not native Protel2 export','ok':not(missing or extra or unattached or shorts),'page':S['source'],'expected_nets':len(expected),'actual_named_nets_with_pins':len(actual),'physical_components':len({c['designator'] for c in S['components']}),'actual_pins':len(pinrows),'native_line_segments':len(segments),'missing':missing,'extra':extra,'unattached_pins':unattached,'shorts':shorts,'pins':pinrows,'native_netlist_available':bool(S.get('netlist'))}
(O/(args.name+'-connection-check.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['pins','page']},indent=2))
