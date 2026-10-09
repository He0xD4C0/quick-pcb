#!/usr/bin/env python3
"""Native library loading fixture, NOT the amplifier topology or delivery."""
import json,zipfile,hashlib,argparse
from pathlib import Path
from capture_parts import parse
R=Path(__file__).resolve().parents[1];lock=json.loads((R/'parts.lock.json').read_text())['parts']
args=argparse.ArgumentParser(description=__doc__)
args.add_argument('--allow-incomplete-library-test',action='store_true',help='Explicitly reproduce an incomplete diagnostic fixture; never use as an amplifier')
options=args.parse_args()
# This R5 generator contains no verified socket footprint. Do not silently
# produce another native document that is guaranteed to fail MISSDEVICE/PIN2PAD.
if not options.allow_incomplete_library_test:
 raise SystemExit('FIXTURE_FOOTPRINT_UNRESOLVED: this legacy fixture generator has no reviewed socket footprint. Use the saved fixture for diagnostics; complete physical library binding before full schematic generation.')

def uid(s):return hashlib.sha256(('6h30-rebuild-load-fixture-r5-20260927:'+s).encode()).hexdigest()[:32]
def dump(rows):return '|\n'.join(json.dumps(h,separators=(',',':'))+'||'+json.dumps(v,separators=(',',':')) for h,v in rows)
class Doc:
 def __init__(self,t,name):self.rows=[({'type':'DOCHEAD'},{'docType':t,'uuid':uid(name),'editVersion':'3.2.186'})]
 def add(self,t,i,**v):self.rows.append(({'type':t,'id':i,'ticket':len(self.rows)},v))
 def attr(self,i,parent,key,value,x=0,y=0,visible=False):self.add('ATTR','attr'+str(len(self.rows)),parentId=parent,key=key,value=value,x=x,y=y,keyVisible=False,valueVisible=visible,fontSize=11,align='LEFT_BOTTOM',rotation=0,version='2.0')
 def poly(self,i,p,part):self.add('POLY',i,partId=part,points=[{'x':x,'y':y} for x,y in p],strokeWidth=1,strokeColor='#800000',fillColor=None,fillStyle='None',closed=False,zIndex=1)
 def pin(self,part,n,name,x,y,rotation):
  i='pin'+n;self.add('PIN',i,partId=part,x=x,y=y,length=20,rotation=rotation,display=True,pinShape='NONE')
  for key,v in [('Pin Number',n),('Pin Name',name),('Pin Type','Passive')]:self.attr(i+key,i,key,v)
 def text(self,i,text,x,y,part=None):self.add('TEXT',i,value=text,x=x,y=y,fontSize=12,align='LEFT_BOTTOM',rotation=0,version='2.0',**({'partId':part} if part else {}))
docs=[]
for key in ['r_10k_025w','jack_trs','pot_dual10k_log']:
 p=lock[key]
 with zipfile.ZipFile(R/p['archive']) as z:
  raw='|\n'.join(z.read(n).decode() for n in z.namelist() if n.endswith('.elibu'))
  for id,d in parse(raw).items():docs.append(dump([({'type':'DOCHEAD'},d['head']),*d['rows'].values()]))
  for id,d in json.loads(z.read('device2.json'))['devices'].items():
   dd=Doc('DEVICE',id);dd.rows[0][1]['uuid']=id;dd.add('META','META',title=d['display_title'],attributes=d['attributes'],description=d.get('description',''),source=d['path']);docs.append(dump(dd.rows))
s=Doc('SYMBOL','tube-symbol')
import math
for part,pp,gg,kk in [('A','6','7','8'),('B','1','2','3')]:
 s.add('PART',part,BBOX=[-70,-70,50,70],title=part)
 s.poly(part+'circle',[(40*math.cos(i*math.pi/24),40*math.sin(i*math.pi/24)) for i in range(49)],part)
 s.poly(part+'plate',[(-22,-25),(22,-25)],part);s.poly(part+'plead',[(0,-50),(0,-25)],part)
 s.poly(part+'cathode',[(-20,25),(20,25),(20,50)],part)
 s.poly(part+'glead',[(-50,0),(-30,0)],part)
 for j in range(4):s.poly(part+'grid'+str(j),[(-27+j*15,0),(-18+j*15,0)],part)
 for n,name,x,y,a in [(pp,'P',0,-70,270),(gg,'G',-70,0,0),(kk,'K',20,70,90)]:s.pin(part,n,name,x,y,a);s.text('lbl'+n,n+':'+name,x+5,y-5,part)
s.add('PART','H',BBOX=[-70,-35,90,40],title='H')
s.poly('heater',[(-50,0),(-30,0),(-20,-10),(-10,10),(0,-10),(10,10),(20,-10),(30,0),(50,0)],'H')
s.pin('H','4','H',-70,0,0);s.pin('H','5','H',70,0,180);s.pin('H','9','SCREEN',0,60,90);s.poly('screen',[(-35,25),(35,25),(35,40),(0,40)],'H');s.text('hlabel','4 / HEATER / 5; SCREEN9',-65,-25,'H')
s.add('META','META',title='QPCB_6H30Pi_EB_REVIEWED_PINS_R5',docType=2,source='quickpcb/rebuild/6h30pi-eb/symbol-r5',description='EHX6H30Pi-EB.pdf p1; physical pins reviewed; no socket footprint')
docs.append(dump(s.rows));d=Doc('DEVICE','tube-device');d.add('META','META',title='QPCB_6H30Pi_EB_REVIEWED_PINS_R5',attributes={'Symbol':uid('tube-symbol'),'Footprint':'','Designator':'V?','Name':'6H30Pi-EB','Manufacturer':'Electro-Harmonix','Manufacturer Part':'6H30Pi-EB','Add into BOM':'yes','Convert to PCB':'no'});docs.append(dump(d.rows))
sch=Doc('SCH','fixture-schematic');sch.add('META','META',title='6H30Pi-Library-Fixture-R5',board='');docs.append(dump(sch.rows))
p=Doc('SCH_PAGE','fixture-page');p.add('CANVAS','CANVAS',originX=0,originY=0);p.add('META','META',title='OneSheet',schematic=uid('fixture-schematic'),zIndex=1);p.text('title','LIBRARY LOAD TEST ONLY — NOT AN AMPLIFIER',100,60)
placements=[]
for ref,key,part,x,y in [('R1','r_10k_025w',None,150,200),('J1','jack_trs',None,400,200),('RV1','pot_dual10k_log',None,700,200),('V1','tube','A',150,500),('V1','tube','B',400,500),('V1','tube','H',700,500)]:
 if key=='tube':device,symbol=uid('tube-device'),uid('tube-symbol');props={'Name':'6H30Pi-EB','Footprint':'','Convert to PCB':'no'}
 else:
  q=lock[key];device,symbol=q['device_uuid'],q['symbol_uuid'];part=part or q['pins'][0]['part'];props=q['library_properties']
 i='component'+str(len(placements));p.add('COMPONENT',i,partId=part,x=x,y=y,rotation=0,isMirror=False,attrs={},zIndex=1)
 for k,v in {**props,'Device':device,'Symbol':symbol,'Designator':ref,'Unique ID':uid('physical-'+ref)}.items():p.attr(i+k,i,k,v,x-50,y-90 if k=='Designator' else y-75,k in ['Designator','Name'])
 placements.append({'ref':ref,'part':part,'key':key,'x':x,'y':y})
docs.append(dump(p.rows));out=R/'evidence/eda/library-fixture.epro2'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('project2.json',json.dumps({'title':'6H30Pi-Library-Fixture','cbb_project':False,'editorVersion':'3.2.186','tags':'[]'}));z.writestr('fixture.epru','|\n'.join(docs))
(R/'evidence/eda/fixture-plan.json').write_text(json.dumps({'purpose':'library-load-test-only','schematic_uuid':uid('fixture-schematic'),'page_uuid':uid('fixture-page'),'placements':placements,'custom_symbol_uuid_before_import':uid('tube-symbol'),'custom_device_uuid_before_import':uid('tube-device')},indent=2)+'\n')
print(out)
