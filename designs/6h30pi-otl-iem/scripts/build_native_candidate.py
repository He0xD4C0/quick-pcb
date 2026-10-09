#!/usr/bin/env python3
"""Build editable one-sheet candidate from locked library archives and fresh topology.
No generated PCB footprints; custom symbols explicitly retain unresolved bindings.
"""
import json,zipfile,hashlib,math
from pathlib import Path
from capture_parts import parse
R=Path(__file__).resolve().parents[1]
L=json.loads((R/'parts.lock.json').read_text())['parts'];E=json.loads((R/'parts.exceptions.json').read_text())['parts']
B=json.loads((R/'topology-candidate.json').read_text())
OUT=R/'evidence/eda';OUT.mkdir(exist_ok=True)
def uid(s):return hashlib.sha256(('6h30-candidate-one-sheet-v1:'+s).encode()).hexdigest()[:16]
def dump(rows):return '|\n'.join(json.dumps(h,separators=(',',':'))+'||'+json.dumps(v,separators=(',',':'),ensure_ascii=False) for h,v in rows)
all_generated=[]
class Doc:
 def __init__(self,t,name):
  self.type=t;self.name=name;self.rows=[({'type':'DOCHEAD'},{'docType':t,'uuid':uid(name),'client':uid('client'),'version':'3.0','editVersion':'3.2.186','updateTime':0})];all_generated.append(self)
 def add(self,t,ident,**v):
  i=ident if ident in ['META','CANVAS'] or t=='PART' else uid(self.name+':'+ident)
  if t in ['COMPONENT','PIN','POLY','ATTR','TEXT']:v={'groupId':'','locked':False,'zIndex':1,**v}
  self.rows.append(({'type':t,'id':i,'ticket':len(self.rows)},v));return i
 def textfields(self,x,y,size=11):return dict(x=x,y=y,rotation=0,color=None,fillColor=None,fontFamily='default',fontSize=size,strikeout=False,underline=False,italic=False,fontWeight=None,align='LEFT_BOTTOM',version='2.0')
 def attr(self,parent,key,value,x=0,y=0,visible=False):
  return self.add('ATTR','attr'+str(len(self.rows)),parentId=parent,key=key,value=str(value),keyVisible=False,valueVisible=visible,**self.textfields(x,y))
 def text(self,text,x,y,size=13,part=None):return self.add('TEXT','text'+str(len(self.rows)),value=text,**self.textfields(x,y,size),**({'partId':part} if part else {}))
 def poly(self,points,part=None):return self.add('POLY','poly'+str(len(self.rows)),points=[dict(x=x,y=y) for x,y in points],strokeWidth=1,strokeColor=None,strokeStyle=None,fillColor=None,fillStyle='NONE',closed=False,startShape=None,endShape=None,**({'partId':part} if part else {}))
 def pin(self,part,n,name,x,y,angle):
  i=self.add('PIN','pin'+part+n,partId=part,x=x,y=y,length=20,rotation=angle,display=True,pinShape='NONE',color=None)
  for k,v in [('Pin Number',n),('Pin Name',name),('Pin Type','Passive')]:self.attr(i,k,v)
  self.text(n+' '+name,x+5,y-4,10,part)

docs={};bindings={}
for key in sorted({p['key'] for p in B['parts']} & L.keys()):
 p=L[key]
 with zipfile.ZipFile(R/p['archive']) as z:
  for n in z.namelist():
   if n.endswith('.elibu'):
    for id,d in parse(z.read(n).decode()).items():docs[id]=dump([({'type':'DOCHEAD'},d['head']),*d['rows'].values()])
  for id,d in json.loads(z.read('device2.json'))['devices'].items():
   dd=Doc('DEVICE',id);dd.rows[0][1]['uuid']=id
   dd.add('META','META',title=d['display_title'],attributes=d['attributes'],description=d.get('description',''),source=d['path']+'/'+id,tags=[],images=[])
   docs[id]=dump(dd.rows)
 bindings[key]={'device':p['device_uuid'],'symbol':p['symbol_uuid'],'props':p['library_properties'],'parts':[p['pins'][0]['part']]}
# Datasheet exceptions. Separate drawn units share physical Unique ID.
for key in sorted({p['key'] for p in B['parts']} - L.keys()):
 s=Doc('SYMBOL','symbol-'+key);parts=['A'];name=E.get(key,{}).get('mpn','T1 custom / TERMINALS UNCONFIRMED')
 if key=='tube_6h30pi_eb':
  parts=['A','B','H']
  for part,pp,gg,kk in [('A','6','7','8'),('B','1','2','3')]:
   s.add('PART',part,BBOX=[-70,-70,50,70],title=part)
   s.poly([(40*math.cos(i*math.pi/24),40*math.sin(i*math.pi/24)) for i in range(49)],part)
   s.poly([(-22,-25),(22,-25)],part);s.poly([(0,-50),(0,-25)],part)
   s.poly([(-20,25),(20,25),(20,50)],part);s.poly([(-50,0),(-30,0)],part)
   for j in range(4):s.poly([(-27+j*15,0),(-18+j*15,0)],part)
   for n,f,x,y,a in [(pp,'P',0,-70,270),(gg,'G',-70,0,0),(kk,'K',20,70,90)]:s.pin(part,n,f,x,y,a)
  s.add('PART','H',BBOX=[-70,-35,90,65],title='H')
  s.poly([(-50,0),(-30,0),(-20,-10),(-10,10),(0,-10),(10,10),(20,-10),(30,0),(50,0)],'H')
  s.poly([(-35,25),(35,25),(35,40),(0,40)],'H')
  for n,f,x,y,a in [('4','H',-70,0,0),('5','H',70,0,180),('9','SCREEN',0,60,90)]:s.pin('H',n,f,x,y,a)
 else:
  s.add('PART','A',BBOX=[-90,-100,90,100],title='A')
  if key=='relay_hv':
   s.poly([(-60,-20),(-35,-20),(25,-45)],'A');s.poly([(35,-20),(60,-20)],'A')
   s.poly([(-60,55),(-40,55),(-40,35),(40,35),(40,75),(-40,75),(-40,55)],'A');s.poly([(40,55),(60,55)],'A')
   pp=[('1','NO',-80,-20,0),('4','NO',80,-20,180),('2','COIL+',-80,55,0),('3','COIL-',80,55,180)]
  elif key=='mains_switch':
   pp=[]
   for left,right,y in [('1','1a',-35),('2','2a',35)]:
    s.poly([(-60,y),(-35,y),(30,y-20)],'A');s.poly([(35,y),(60,y)],'A');pp.extend([(left,'IN',-80,y,0),(right,'OUT',80,y,180)])
   s.poly([(0,-40),(0,20)],'A')
  elif key=='mains_inlet':
   s.poly([(-50,-60),(50,-60),(50,70),(-50,70),(-50,-60)],'A');pp=[('L','LINE',70,-40,180),('N','NEUTRAL',70,0,180),('PE','EARTH',70,40,180)]
  elif key=='transformer_contract':
   s.poly([(-12,-90),(-12,90)],'A');s.poly([(12,-90),(12,90)],'A')
   for yy in range(-80,81,20):s.poly([(-40,yy),(-60,yy+5),(-60,yy+15),(-40,yy+20)],'A')
   for yy in [-80,-20,40]:s.poly([(40,yy),(60,yy+5),(60,yy+15),(40,yy+20)],'A')
   pp=[('1','220V',-80,-80,0),('2','PRI',-80,80,0),('3','150V',80,-80,180),('4','HV',80,-60,180),('5','9.5V',80,-20,180),('6','HTR',80,0,180),('7','12V',80,40,180),('8','AUX',80,60,180)]
  else:raise ValueError(key)
  for p in pp:s.pin('A',*p)
 s.add('META','META',title=name,description='Datasheet symbol; footprint unresolved. '+('Proposed transformer terminals only.' if key=='transformer_contract' else ''),tags=[],source='quickpcb/candidate-v1/'+key,docType=2)
 docs[uid('symbol-'+key)]=dump(s.rows)
 d=Doc('DEVICE','device-'+key);props={'Symbol':uid('symbol-'+key),'Footprint':'','Name':name,'Designator':'X?','Manufacturer Part':name,'Add into BOM':'yes','Convert to PCB':'yes'}
 d.add('META','META',title=name,attributes=props,source='quickpcb/candidate-v1/device/'+key,tags=[],images=[])
 docs[uid('device-'+key)]=dump(d.rows);bindings[key]={'device':uid('device-'+key),'symbol':uid('symbol-'+key),'props':props,'parts':parts}

sch=Doc('SCH','schematic');sch.add('META','META',title='6H30Pi-Stereo-CANDIDATE',board='',source='',zIndex=1);docs[uid('schematic')]=dump(sch.rows)
p=Doc('SCH_PAGE','page');p.add('CANVAS','CANVAS',originX=0,originY=0)
p.add('META','META',title='Stereo-Amp-Power-Protection',schematic=uid('schematic'),source='',zIndex=1)
p.text('6H30Pi STEREO WCF / HIGH & LOW / COMPLETE AC POWER',100,60,26)
p.text('CANDIDATE REV A | 2026-09-27 | UNQUALIFIED: DO NOT ENERGIZE / NO HEADPHONES',100,98,18)
p.text('One sheet / genuine JLC library parts + disclosed datasheet exceptions / all voltages are design targets, not measurements',100,125,14)
sections=[(80,170,1030,750,'01 INPUT / HIGH-LOW / VOLUME'),(1180,170,2450,1030,'02 LEFT / PURE TUBE WCF'),(2580,170,3850,1030,'03 RIGHT / PURE TUBE WCF'),(3970,170,4600,750,'04 3.5mm OUTPUT'),(80,1070,1080,1950,'05 220VAC / ISOLATION'),(1180,1050,2480,1950,'06 B+ DISCRETE REGULATOR'),(2600,1050,4250,1950,'07 6.3V DC HEATERS / ELEVATION'),(80,2070,1260,2730,'08 AUXILIARY DC'),(1390,2070,2660,2730,'09 DELAY / RELAY DRIVE'),(2780,2070,4490,2730,'10 BIPOLAR DC FAULT SENSE')]
for x,y,x2,y2,t in sections:p.poly([(x,y+30),(x2,y+30)]);p.text(t,x,y,18)
placements=[]
for ins in B['parts']:
 q=bindings[ins['key']];x,y=ins['x'],ins['y'];ref=ins['ref']
 for part in q['parts']:
  yy=y+({'A':0,'B':280,'H':495}[part] if ins['key']=='tube_6h30pi_eb' else 0)
  i=p.add('COMPONENT',ref+part,partId=part,x=x,y=yy,rotation=(-ins['angle'])%360,isMirror=False,attrs={})
  props={**q['props'],'Device':q['device'],'Symbol':q['symbol'],'Designator':ref,'Unique ID':uid('physical-'+ref)}
  # Keep true value/rating visible without long manufacturer strings over wires.
  name=props.get('Value') or props.get('Manufacturer Part') or props.get('Name','')
  if ins['key'].startswith('r_'):name+=' / '+props.get('Power(Watts)','')
  if ins['key'].startswith('c_'):name+=' / '+props.get('Rated Voltage',props.get('Voltage - Rated',''))
  props['Name']=name
  for k,v in props.items():p.attr(i,k,v,x+30,yy-30 if k=='Designator' else yy-15,k in ['Designator','Name'])
  placements.append(dict(id=i,ref=ref,key=ins['key'],part=part,x=x,y=yy,angle=ins['angle'],section=ins['section']))
for n in B['notes']:p.text(n['text'],n['x'],n['y'],12)
p.text('STATUS: drawn candidate only. Native DRC / connectivity / electrical acceptance are recorded separately in delivery/REPORT.md.',100,2830,16)
docs[uid('page')]=dump(p.rows)
with zipfile.ZipFile(OUT/'candidate-unwired.epro2','w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('project2.json',json.dumps({'title':'6H30Pi-Stereo-CANDIDATE','cbb_project':False,'editorVersion':'3.2.186','tags':'[]'}));z.writestr('candidate.epru','|\n'.join(docs.values()))
(OUT/'candidate-generated-rows.json').write_text(json.dumps([dict(doc=d.type,rows=d.rows) for d in all_generated]))
(OUT/'candidate-placement.json').write_text(json.dumps(placements,indent=2))
print('docs',len(docs),'physical',len(B['parts']),'drawn units',len(placements))
