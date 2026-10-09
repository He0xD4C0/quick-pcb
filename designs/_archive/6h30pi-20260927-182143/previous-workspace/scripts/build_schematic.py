#!/usr/bin/env python3
"""Generate native EasyEDA Pro epro2 plus vector PDF from one connection manifest.
No invented vendor/library identities: deterministic project-owned symbol UUIDs.
All contacts have physical wires plus visible NET names; cross-page nets enabled.
"""
from pathlib import Path
import json,hashlib,zipfile,math,textwrap
ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'circuit.json').read_text());T=DATA['types'];COMPS=DATA['components']
PAGE_W,PAGE_H=842,1191

def uid(s):return hashlib.sha256(('6h30-candidate-v01:'+s).encode()).hexdigest()[:16]
class Doc:
 def __init__(self,typ,key):
  self.rows=[({'type':'DOCHEAD'},{'docType':typ,'uuid':uid(key),'client':'qpcb6h30','editVersion':'3.2.186'})]
 def add(self,typ,id,**v):self.rows.append((dict(type=typ,id=id,ticket=len(self.rows)),v))
 def text(self,id,value,x,y,size=10,color='#152C46'):
  self.add('TEXT',id,value=value,x=x,y=-y,fontSize=size,align='LEFT_BOTTOM',rotation=0,zIndex=1,color=color,version='2.0')
 def attr(self,id,parent,key,value,x=None,y=None,visible=False,size=9):
  self.add('ATTR',id,parentId=parent,key=key,value=value,x=x,y=-y if y is not None else None,keyVisible=False,valueVisible=visible,fontSize=size,align='LEFT_BOTTOM',rotation=0,version='2.0')
 def dump(self):
  # Native source Y increases downward; Bridge API Y has the opposite sign.
  rows=[]
  for a,b in self.rows:
   b=dict(b)
   for key in ['y','startY','endY','dotY1','dotY2']:
    if isinstance(b.get(key),(int,float)):b[key]=-b[key]
   if 'points' in b:b['points']=[dict(p,y=-p['y']) for p in b['points']]
   rows.append(json.dumps(a,separators=(',',':'))+'||'+json.dumps(b,separators=(',',':')))
  return '|\n'.join(rows)

def pins(typ):
 pp=T[typ];nl=(len(pp)+1)//2;nr=len(pp)//2;out=[]
 for i,(no,name) in enumerate(pp):
  left=i<nl;index=i if left else i-nl;total=nl if left else nr
  out.append((no,name,-48 if left else 48, (index-(total-1)/2)*16,left))
 return out
NOTES={
'01':['HIGH: SW1 C-H. LOW: C-L, nominal -20 dB with 10k volume loading.','Both gangs share a shaft. Turn volume down before changing gain or plugging headphones.','J1/J2 T=left, R=right, S=audio return; sleeve/chassis insulated except LK1 star bond.'],
'02':['V1 wiring view: pin 6/7/8 = upper P/G/K; 1/2/3 = lower P/G/K; 4/5 heater; 9 shield.','Nominal: P1 ~155.4V, G1 80.0V, K1/P2 82.1V, G2 0V, K2 2.49V; Iq 36.6mA.','Plate power upper ~2.68W / lower ~2.91W. CO+ faces MID. Relay does not qualify cap-short safety.'],
'03':['V2 identical to V1. One complete dual triode per channel; 6.3V heaters in parallel.','WCF local feedback: plate PA -> CF -> GB -> lower grid; RK bypass CK sets AC balance.','127 ohm RS balances both model fits, not a universal tube constant. No real-headphone testing yet.'],
'04':['220 VAC / 50 Hz, evaluate 198..242 VAC. Primary, HV, heater and aux are separate windings.','PE is bolted directly to chassis and transformer screen; never fused or switched.','T1 custom specification at LOAD; rated insulation, winding regulation and inrush require supplier review.'],
'05':['QHV pins G/D/S = 1/2/3; tab=D. QERR/QIL pins E/B/C=1/2/3.','HV output nominal ~160V. Gate clamp DGS protects Vgs; QIL senses RIS at roughly 0.13A.','Heatsink <=8 C/W, insulated. MOSFET continuous linear SOA / loop stability are NOT qualified.'],
'06':['Heater output is FLOATING: HMINUS ~38V above AGND. HPLUS=HMINUS+6.3V.','LM1084 pin 1 ADJ / 2 OUT / 3 IN, tab=OUT. Insulate heatsink; target <=1.5 C/W.','CHOUT aluminum ESR is intentional. Aux regulator QAUX emitter output approximately 12V.'],
'07':['Timer RT/CT with 5.1V zener and Darlington driver; typical delay must be read from simulation.','QAC/QKILL rapidly reset TIMER on missing AC pulses. Flyback uses diode + 24V zener.','DC monitors on sheets 8/9 discharge TIMER. This candidate has NOT passed capacitor-short protection.'],
'08':['DC sense = (AUX12 + L_OUT)/2; 100k/100k and 1u low-pass remove audio.','Differential pairs compare against REFHI/REFLO; reverse B-E diodes protect the transistors.','Fault path resets TIMER through diodes. Detector speed and contact stress are release-blocking tests.'],
'09':['DC sense = (AUX12 + R_OUT)/2. Either channel can inhibit both relay coils.','No dedicated protection IC. All detector NPNs are MPSA42, E/B/C=1/2/3.','READINESS: engineering candidate only; no PCB, no physical measurements, no real IEM connection.']}

def main():
 from reportlab.pdfgen import canvas
 from reportlab.lib.colors import HexColor
 out=ROOT/'schematic';out.mkdir(exist_ok=True)
 pdfpath=ROOT/'output/pdf/6H30Pi-OTL-schematic.pdf';pdfpath.parent.mkdir(parents=True,exist_ok=True)
 pdf=canvas.Canvas(str(pdfpath),pagesize=(PAGE_W,PAGE_H));pdf.setTitle('Dual 6H30Pi OTL - schematic candidate v0.1')
 docs=[]
 for typ in T:
  sd=Doc('SYMBOL','sym'+typ);pp=pins(typ);height=max(24,math.ceil(len(pp)/2)*16+8)
  sd.add('PART','P',BBOX=[-48,-height/2,48,height/2],title='P')
  if typ not in ['C','D']:
   sd.add('RECT','body',partId='P',dotX1=-34,dotY1=height/2,dotX2=34,dotY2=-height/2,strokeWidth=1,strokeColor='#243F60',fillColor=None,fillStyle='None',radiusX=0,radiusY=0,rotation=0)
  else:
   segs=[(-34,0,-5,0),(5,0,34,0),(-5,-12,-5,12),(5,-12,5,12)] if typ=='C' else [(-34,0,-12,0),(-12,-12,-12,12),(-12,12,12,0),(-12,-12,12,0),(12,-12,12,12),(12,0,34,0)]
   for j,(x1,y1,x2,y2) in enumerate(segs):sd.add('POLY','shape'+str(j),partId='P',points=[dict(x=x1,y=y1),dict(x=x2,y=y2)],strokeWidth=1,strokeColor='#243F60',fillColor=None,fillStyle='None')
  for no,name,x,y,left in pp:
   pid='pin'+no;sd.add('PIN',pid,partId='P',x=x,y=-y,length=14,rotation=0 if left else 180,display=True,pinShape='NONE')
   for key,val in [('Pin Number',no),('Pin Name',name),('Pin Type','Passive')]:sd.attr(pid+key,pid,key,val,visible=False)
   sd.add('TEXT',pid+'label',partId='P',value=no+':'+({'COIL_A':'C+','COIL_B':'C-','CONTACT_A':'IN','CONTACT_B':'OUT','SCREEN':'SH','TIP_L':'L','RING_R':'R','SLEEVE':'GND'}.get(name,name[:4])),x=-30 if left else 3,y=-y-20 if typ in ['C','D'] else -y+2,fontSize=6,align='LEFT_BOTTOM',rotation=0,zIndex=4,version='2.0')
  sd.add('META','META',title='QPCB_'+typ,docType=2,source='Project authored from cited pin maps');docs.append(sd)
  dd=Doc('DEVICE','dev'+typ);dd.add('META','META',title='QPCB_'+typ,attributes={'Symbol':uid('sym'+typ),'Designator':'X?','Name':typ,'Add into BOM':'yes','Convert to PCB':'no','Footprint':''});docs.append(dd)
 schid=uid('schematic');sch=Doc('SCH','schematic');sch.add('META','META',title='6H30Pi_OTL_candidate_v01',board='');docs.append(sch)
 pages=sorted(set(c['page'] for c in COMPS));placement=[]
 for pi,page in enumerate(pages):
  sd=Doc('SCH_PAGE',page);sd.add('CANVAS','CANVAS',originX=0,originY=0);sd.add('META','META',title=page,schematic=schid,zIndex=pi+1)
  title=page.replace('_',' ')
  sd.text('title','TWO 6H30Pi | '+title,35,42,19);sd.text('status','v0.1 CANDIDATE / NOT QUALIFIED FOR REAL HEADPHONES',35,65,11,'#A03022')
  pdf.setFillColor(HexColor('#152C46'));pdf.setFont('Helvetica-Bold',19);pdf.drawString(35,PAGE_H-42,'TWO 6H30Pi | '+title)
  pdf.setFillColor(HexColor('#A03022'));pdf.setFont('Helvetica-Bold',11);pdf.drawString(35,PAGE_H-65,'v0.1 CANDIDATE / NOT QUALIFIED FOR REAL HEADPHONES')
  for k,note in enumerate(NOTES[page[:2]]):
   sd.text('note'+str(k),note,35,88+13*k,8)
   pdf.setFillColor(HexColor('#243F60'));pdf.setFont('Helvetica',8);pdf.drawString(35,PAGE_H-88-13*k,note)
  pc=[x for x in COMPS if x['page']==page]
  for i,comp in enumerate(pc):
   x=145+(i%3)*268;y=210+(i//3)*132;typ=comp['type'];ref=comp['ref'];ps=pins(typ);height=max(24,math.ceil(len(ps)/2)*16+8)
   sd.add('COMPONENT',ref,partId='P',x=x,y=-y,rotation=0,isMirror=False,attrs={},zIndex=1)
   for key,value in [('Device',uid('dev'+typ)),('Symbol',uid('sym'+typ)),('Designator',ref),('Name',comp['value']),('Footprint',''),('Add into BOM','yes'),('Convert to PCB','no')]:
    sd.attr(ref+'_'+key,ref,key,(value+' ['+comp['alias']+']') if key=='Name' else value,x-100,y-max(48,height/2+26) if key=='Designator' else y-max(48,height/2+26)+13,visible=key in ['Designator','Name'],size=10 if key=='Designator' else 8)
   pdf.setFillColor(HexColor('#152C46'));pdf.setFont('Helvetica-Bold',10);pdf.drawString(x-110,PAGE_H-y+max(48,height/2+26),ref)
   pdf.setFont('Helvetica',8);pdf.drawString(x-110,PAGE_H-y+max(48,height/2+26)-13,comp['value']+' ['+comp['alias']+']')
   pdf.setStrokeColor(HexColor('#243F60'));pdf.setLineWidth(.75);
   if typ not in ['C','D']:pdf.rect(x-34,PAGE_H-y-height/2,68,height,fill=0)
   else:
    segs=[(-34,0,-5,0),(5,0,34,0),(-5,-12,-5,12),(5,-12,5,12)] if typ=='C' else [(-34,0,-12,0),(-12,-12,-12,12),(-12,12,12,0),(-12,-12,12,0),(12,-12,12,12),(12,0,34,0)]
    for x1,y1,x2,y2 in segs:pdf.line(x+x1,PAGE_H-y+y1,x+x2,PAGE_H-y+y2)
   for no,name,dx,dy,left in ps:
    nx=x+dx;ny=y+dy;outer=nx+(-56 if left else 56);net=comp['pins'][no];wid=ref+'w'+no
    sd.add('WIRE',wid,zIndex=2);sd.add('LINE',wid+'line',lineGroup=wid,startX=nx,startY=-ny,endX=outer,endY=-ny,strokeWidth=1,strokeColor='#15705B')
    lx=outer if left else nx+5
    sd.attr(wid+'net',wid,'NET',net,lx,ny-3,True,7)
    pdf.setStrokeColor(HexColor('#15705B'));pdf.line(outer,PAGE_H-ny,x+(-34 if left else 34),PAGE_H-ny)
    pdf.setFillColor(HexColor('#15705B'));pdf.setFont('Helvetica',7);pdf.drawString(lx,PAGE_H-ny+3,net)
    pdf.setFillColor(HexColor('#243F60'));pdf.setFont('Helvetica',6);pdf.drawString(x+(-30 if left else 3),PAGE_H-ny-20 if typ in ['C','D'] else PAGE_H-ny+2,no+':'+({'COIL_A':'C+','COIL_B':'C-','CONTACT_A':'IN','CONTACT_B':'OUT','SCREEN':'SH','TIP_L':'L','RING_R':'R','SLEEVE':'GND'}.get(name,name[:4])))
   rating=comp['rating']
   # Annotation separate from the electrical primitive; preserve full rating in BOM.
   for j,line in enumerate(textwrap.wrap(rating,53)[:2]):
    sd.text(ref+'rating'+str(j),line,x-110,y+51+j*10,7)
    pdf.setFillColor(HexColor('#555555'));pdf.setFont('Helvetica',7);pdf.drawString(x-110,PAGE_H-y-51-j*10,line)
   placement.append(dict(ref=ref,page=page,x=x,y=y,pins=[dict(number=no,x=x+dx,y=y+dy,net=comp['pins'][no]) for no,_,dx,dy,_ in ps]))
  foot='GLOBAL NET LABELS CONNECT ACROSS SHEETS | Physical pins stated; panel/relay terminals functional | NO PCB FOOTPRINTS'
  sd.text('footer',foot,35,1155,7);pdf.setFont('Helvetica',7);pdf.setFillColor(HexColor('#555555'));pdf.drawString(35,36,foot);pdf.drawRightString(808,20,f'{pi+1} / {len(pages)} - 2026-09-27')
  docs.append(sd);pdf.showPage()
 pdf.save()
 cfg=Doc('CONFIG','CONFIG');cfg.rows[0][1]['uuid']='CONFIG';cfg.add('UNIVERSAL','UNIVERSAL',allowLibRename=True,defaultNetName=True,wireMultipleNet=True,netFlagCrossLayerConnection=True,netLabelCrossPageConnection=True);docs.append(cfg)
 text='|\n'.join(doc.dump() for doc in docs)
 (out/'6H30Pi-OTL.epru').write_text(text)
 with zipfile.ZipFile(out/'6H30Pi-OTL.epro2','w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('project2.json',json.dumps({'title':DATA['name'],'cbb_project':False,'editorVersion':'3.2.186','tags':'[]'}))
  z.writestr('6H30Pi-OTL.epru',text)
 (out/'placement.json').write_text(json.dumps(placement,indent=2)+'\n')
 print(pdfpath);print(out/'6H30Pi-OTL.epro2')
if __name__=='__main__':main()
