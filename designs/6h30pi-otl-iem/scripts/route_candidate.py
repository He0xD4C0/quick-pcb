#!/usr/bin/env python3
"""Route local orthogonal connections from actual EDA pin readback; use NET at boundaries."""
import json,math,heapq,itertools
from collections import defaultdict
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'evidence/eda'
B=json.loads((R/'topology-candidate.json').read_text());S=json.loads((O/'candidate-before-wiring-state.json').read_text());I={p['ref']:p for p in B['parts']}
G=5
q=lambda x:round(x/G)
def xy(x,y):return q(x/10),q(-y/10)
body={};labels=set();occupied={};pins=[];wires=[];markers=[]
def rect(x1,y1,x2,y2):return [(x,y) for x in range(q(x1),q(x2)+1) for y in range(q(y1),q(y2)+1)]
for c in S['components']:
 b=c['bbox'];body[c['id']]=set(rect(b['minX']/10-5,-b['maxY']/10-5,b['maxX']/10+5,-b['minY']/10+5))
 # text attributes placed upper-right; avoid them, not a substitute for visual inspection.
 x,y=c['x']/10,-c['y']/10;labels.update(rect(x+25,y-45,x+130,y-12))
 for p in c['pins']:
  net=I[c['designator']]['pins'][p['number']]
  if net is None:continue
  a=math.radians(p['rotation']);d=(round(math.cos(a)),round(-math.sin(a)))
  start=xy(p['x'],p['y']);end=(start[0]+d[0]*6,start[1]+d[1]*6)
  pins.append(dict(ref=c['designator'],number=p['number'],net=net,p=start,e=end,d=d,body=c['id'],section=I[c['designator']]['section']))
# Custom pin captions are not electrical obstacles; use the symbol body extent.
for c in S['components']:
 if I[c['designator']]['key'] in ['tube_6h30pi_eb','relay_hv','mains_inlet','mains_switch','transformer_contract']:
  x,y=c['x']/10,-c['y']/10
  half=45 if I[c['designator']]['key']!='transformer_contract' else 62
  body[c['id']]=set(rect(x-half,y-(25 if c['sub_part_name']=='H' else 45),x+half,y+(40 if c['sub_part_name']=='H' else 45)))
blocked=set().union(*body.values())
pin_cells=defaultdict(set)
for p in pins:pin_cells[p['p']].add(p['net'])
def cells(a,b):
 assert a[0]==b[0] or a[1]==b[1],(a,b)
 dx=(b[0]>a[0])-(b[0]<a[0]);dy=(b[1]>a[1])-(b[1]<a[1]);n=abs(b[0]-a[0])+abs(b[1]-a[1])
 return [(a[0]+i*dx,a[1]+i*dy) for i in range(n+1)]
def reserve(path,net):
 for a,b in zip(path,path[1:]):
  for pt in cells(a,b):
   assert pt not in occupied or occupied[pt]==net,('short',pt,occupied.get(pt),net)
   occupied[pt]=net

def simplify(path):
 out=[]
 for p in path:
  if len(out)>=2 and (out[-1][0]-out[-2][0])*(p[1]-out[-1][1])==(out[-1][1]-out[-2][1])*(p[0]-out[-1][0]):out[-1]=p
  else:out.append(p)
 return out

def wire(path,net):
 path=simplify(path)
 if len(path)<2:return
 reserve(path,net);wires.append({'net':net,'points':[[x*G,-y*G] for x,y in path]})
# Escape in the actual pin direction, before any local route.
for p in pins:
 wire([p['p'],p['e']],p['net'])

def free(pt,net,ends):
 if pt in ends:return True
 if pt in occupied:return occupied[pt]==net
 if pt in blocked:return False
 if pin_cells.get(pt,set())-{net}:return False
 # Distinct nets never touch or overlap; one grid clearance is kept.
 for dx,dy in [(0,1),(0,-1),(1,0),(-1,0)]:
  if occupied.get((pt[0]+dx,pt[1]+dy),net)!=net:return False
 return True

def route(a,b,net,limit=16000):
 if a==b:return [a]
 ends={a,b};loX=min(a[0],b[0])-24;hiX=max(a[0],b[0])+24;loY=min(a[1],b[1])-24;hiY=max(a[1],b[1])+24
 h=lambda p:abs(p[0]-b[0])+abs(p[1]-b[1]);heap=[(h(a),0,a,-1)];dist={(a,-1):0};prev={};final=None
 for _ in range(limit):
  if not heap:break
  _,cost,p,di=heapq.heappop(heap)
  if dist.get((p,di))!=cost:continue
  if p==b:final=(p,di);break
  for nd,(dx,dy) in enumerate([(1,0),(0,1),(-1,0),(0,-1)]):
   pp=(p[0]+dx,p[1]+dy)
   if not(loX<=pp[0]<=hiX and loY<=pp[1]<=hiY) or not free(pp,net,ends):continue
   nc=cost+1+(2 if di!=-1 and nd!=di else 0)
   if nc<dist.get((pp,nd),1e20):dist[(pp,nd)]=nc;prev[(pp,nd)]=(p,di);heapq.heappush(heap,(nc+h(pp),nc,pp,nd))
 if final is None:return None
 out=[final[0]]
 while final in prev:final=prev[final];out.append(final[0])
 return list(reversed(out))
parent=list(range(len(pins)))
def find(i):
 while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
 return i
pairs=[]
for a,b in itertools.combinations(range(len(pins)),2):
 pa,pb=pins[a],pins[b]
 if pa['net']!=pb['net'] or pa['section']!=pb['section']:continue
 d=abs(pa['e'][0]-pb['e'][0])+abs(pa['e'][1]-pb['e'][1]);power=pa['net'] in ['AGND','PE','BPLUS','HMINUS','HPLUS','AUX12']
 if d*G<=(300 if power else 650):pairs.append((d,a,b))
for d,a,b in sorted(pairs):
 if find(a)==find(b):continue
 path=route(pins[a]['e'],pins[b]['e'],pins[a]['net'])
 if path:wire(path,pins[a]['net']);parent[find(a)]=find(b)
clusters=defaultdict(list)
for i,p in enumerate(pins):clusters[(p['net'],find(i))].append(i)
netclusters=defaultdict(list)
for (net,k),members in clusters.items():netclusters[net].append(members)
# One marker per disconnected local cluster, never one label per physical pin by default.
failed=[]
for net,groups in netclusters.items():
 power=net in ['AGND','PE','BPLUS','HMINUS','HPLUS','AUX12']
 if len(groups)==1 and not power:continue
 for members in groups:
  success=False
  candidates=sorted(members,key=lambda i:(pins[i]['e'][1],-pins[i]['e'][0]))
  for i in candidates:
   start=pins[i]['e']
   dirs=[(0,1),(1,0),(-1,0),(0,-1)] if net in ['AGND','PE'] else [(1,0),(-1,0),(0,-1),(0,1)]
   for dx,dy in dirs:
    # Reserve enough space for a real marker and readable text.
    for length in [8,12,18,24]:
     target=(start[0]+dx*length,start[1]+dy*length)
     if not free(target,net,set()):continue
     rotation=0 if dx>=0 else 180
     width=(max(40,len(net)*7)+20)/G
     box=rect(target[0]*G+(8 if rotation==0 else -width*G),target[1]*G-12,target[0]*G+(width*G if rotation==0 else -8),target[1]*G+12)
     if any(pt in blocked or pt in labels or occupied.get(pt,net)!=net for pt in box):continue
     path=route(start,target,net,5000)
     if not path:continue
     wire(path,net)
     markers.append(dict(net=net,x=target[0]*G,y=-target[1]*G,rotation=rotation,kind='flag' if power else 'port',identification='AnalogGround' if net=='AGND' else 'ProtectGround' if net=='PE' else 'Power'))
     blocked.update(box);success=True;break
    if success:break
   if success:break
  if not success:
   # Dense connector escape: retain a visible real NET at the existing stub end.
   i=members[0];t=pins[i]['e'];dx,dy=pins[i]['d']
   markers.append(dict(net=net,x=t[0]*G,y=-t[1]*G,rotation=0 if dx>=0 else 180,kind='flag' if power else 'port',identification='AnalogGround' if net=='AGND' else 'Power',dense_escape=True))
result=dict(wires=wires,markers=markers,pins=pins,unmarked_clusters=failed,physical_refs=len(I),net_count=len(netclusters),local_connections=len(wires)-len(pins)-len(markers))
(O/'candidate-routing-plan.json').write_text(json.dumps(result,indent=2));print({k:len(v) if isinstance(v,list) else v for k,v in result.items() if k!='pins'})
assert not failed,failed
