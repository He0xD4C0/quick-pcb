#!/usr/bin/env python3
"""One editable native sheet. Physical connectivity stays in circuit.json.
Hand-placed functional groups; nearby aligned pins are wired directly.
Other connections terminate in native EasyEDA Net Ports, embedded from its library.
"""
from pathlib import Path
import json,hashlib,math,zipfile,collections,re
from library_bindings import binding,documents,SELECTED
ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'circuit.json').read_text());C={x['alias']:x for x in DATA['components']}
NAME='QuickPCB_6H30Pi_OTL_OneSheet_v03'
OUT=ROOT/'schematic/single-sheet';OUT.mkdir(exist_ok=True)
def uid(s):return hashlib.sha256(('6h30-one-sheet-v03:'+s).encode()).hexdigest()[:16]
class Doc:
 def __init__(self,t,k):self.rows=[({'type':'DOCHEAD'},{'docType':t,'uuid':uid(k),'client':'qpcb6h30','editVersion':'3.2.186'})]
 def add(self,t,i,**v):self.rows.append((dict(type=t,id=i,ticket=len(self.rows)),v))
 def text(self,i,value,x,y,size=12,color='#1F3045',part=None):
  self.add('TEXT',i,value=value,x=x,y=y,fontSize=size,align='LEFT_BOTTOM',rotation=0,zIndex=5,color=color,version='2.0',**({'partId':part} if part else {}))
 def poly(self,i,points,part=None):self.add('POLY',i,points=[dict(x=x,y=y) for x,y in points],strokeColor='#5B2323',strokeWidth=1.2,strokeStyle=0,fillColor='',fillStyle=0,closed=False,zIndex=1,**({'partId':part} if part else {}))
 def attr(self,i,parent,key,value,x=0,y=0,visible=False,size=11):self.add('ATTR',i,parentId=parent,key=key,value=value,x=x,y=y,keyVisible=False,valueVisible=visible,fontSize=size,align='LEFT_BOTTOM',rotation=0,version='2.0')
 def dump(self):return '|\n'.join(json.dumps(a,separators=(',',':'))+'||'+json.dumps(b,separators=(',',':')) for a,b in self.rows)
SYMS={};DOCS=[];BINDINGS={};LIBKEYS={'NET'}
def symbol(typ,orient='H'):
 key=typ+orient
 if key in SYMS:return key
 d=Doc('SYMBOL',key);pins={};shapes=[];texts=[]
 def path(*p):shapes.append(list(p))
 def pin(n,x,y,side):pins[n]=(x,y,side)
 if typ in ['R','C','D','Z','F','LINK']:
  a,k=('A','K') if typ in ['D','Z'] else ('1','2');pin(a,-40,0,'L');pin(k,40,0,'R')
  path((-25,0),(-18,0));path((18,0),(25,0))
  if typ=='R':path((-18,-7),(18,-7),(18,7),(-18,7),(-18,-7))
  elif typ=='C':
   path((-25,0),(-5,0));path((5,0),(25,0));path((-5,-16),(-5,16));path((5,-16),(5,16));texts.append(('+',-15,-19,9))
  elif typ in ['D','Z']:
   path((-25,0),(-12,0));path((-12,-12),(12,0),(-12,12),(-12,-12));path((12,-13),(12,13));path((12,0),(25,0))
   if typ=='Z':path((7,-16),(12,-13));path((12,13),(17,16))
  elif typ=='F':path((-20,-8),(20,-8),(20,8),(-20,8),(-20,-8));path((-25,0),(25,0))
  else:path((-25,0),(25,0))
 elif typ in ['NPN','MOS']:
  pin('1',20,50,'D') if typ=='NPN' else pin('1',-50,0,'L')
  pin('2',-50,0,'L') if typ=='NPN' else pin('2',20,-50,'U')
  pin('3',20,-50,'U') if typ=='NPN' else pin('3',20,50,'D')
  path((-35,0),(-12,0));path((-12,-21),(-12,21))
  if typ=='NPN':
   path((-12,-11),(20,-30),(20,-35));path((-12,11),(20,30),(20,35));path((20,30),(10,17),(5,26),(20,30))
  else:
   for yy in [-18,-4,10]:path((-4,yy),(-4,yy+8))
   path((-4,-15),(20,-15),(20,-35));path((-4,15),(20,15),(20,35));path((5,15),(-4,10),(-4,20),(5,15))
 elif typ=='TUBE':
  for n,x,y,side in [('6',0,-170,'U'),('7',-90,-110,'L'),('8',20,-30,'D'),('1',0,30,'U'),('2',-90,100,'L'),('3',20,180,'D'),('4',-60,240,'L'),('5',60,240,'R'),('9',120,210,'R')]:pin(n,x,y,side)
  for cy in [-110,100]:
   path(*[(48*math.cos(a),cy+48*math.sin(a)) for a in [i*2*math.pi/48 for i in range(49)]])
   path((-22,cy-25),(22,cy-25));path((0,cy-25),(0,cy-55))
   for xx in [-27,-12,3,18]:path((xx,cy),(xx+9,cy))
   path((-75,cy),(-30,cy));path((-20,cy+25),(20,cy+25),(20,cy+65))
  path((-45,240),(-30,240),(-20,228),(-10,252),(0,228),(10,252),(20,228),(30,240),(45,240))
  path((105,210),(92,210),(92,-155));texts += [('P1 6',28,-145,10),('G1 7',-76,-124,10),('K1 8',27,-60,10),('P2 1',28,60,10),('G2 2',-76,86,10),('K2 3',27,150,10),('4   HEATER 6.3 V   5',-65,275,10),('SH 9',90,190,10)]
 elif typ=='LDO':
  pin('3',-70,0,'L');pin('2',70,0,'R');pin('1',0,60,'D');path((-55,-25),(55,-25),(55,30),(-55,30),(-55,-25));path((0,30),(0,45));texts += [('IN',-48,-5,10),('OUT',22,-5,10),('ADJ',-12,24,9)]
 elif typ=='RELAY':
  for n,x,y,s in [('A',-80,0,'L'),('B',80,0,'R'),('CA',-60,90,'L'),('CB',60,90,'R')]:pin(n,x,y,s)
  path((-65,0),(-25,0),(20,-28));path((30,0),(65,0));path((-45,75),(45,75),(45,105),(-45,105),(-45,75));path((-45,90),(-25,90),(-15,80),(-5,100),(5,80),(15,100),(25,90),(45,90))
  for yy in [15,35,55]:path((0,yy),(0,yy+10))
 elif typ=='GAIN':
  for pre,yy in [('L',-65),('R',65)]:
   pin(pre+'C',-80,yy,'L');pin(pre+'H',80,yy-25,'R');pin(pre+'L',80,yy+25,'R');path((-65,yy),(-28,yy),(30,yy-25),(65,yy-25));path((30,yy+25),(65,yy+25));texts += [('H',40,yy-32,10),('L',40,yy+42,10)]
  for yy in range(-45,46,20):path((0,yy),(0,yy+10))
 elif typ=='POT':
  for pre,xx in [('L',-65),('R',65)]:
   pin(pre+'T',xx,-80,'U');pin(pre+'B',xx,80,'D');pin(pre+'W',xx+45,0,'R');path((xx,-65),(xx,-38),(xx-8,-38),(xx-8,38),(xx+8,38),(xx+8,-38),(xx,-38));path((xx,38),(xx,65));path((xx+30,0),(xx+10,0),(xx+19,-6));path((xx+10,0),(xx+19,6))
 elif typ=='SW':
  for pre,yy in [('L',-35),('N',35)]:pin(pre+'1',-60,yy,'L');pin(pre+'2',60,yy,'R');path((-45,yy),(-20,yy),(20,yy-18));path((25,yy),(45,yy))
  path((0,-20),(0,20))
 elif typ=='TX':
  pin('P1',-95,-80,'L');pin('P2',-95,80,'L');pin('SH',0,215,'D');path((-80,-80),(-55,-80));path((-80,80),(-55,80));path((-12,-155),(-12,165));path((12,-155),(12,165));path((0,185),(0,200))
  for n1,n2,cy in [('H1','H2',-110),('F1','F2',10),('A1','A2',130)]:
   pin(n1,95,cy-30,'R');pin(n2,95,cy+30,'R');path((80,cy-30),(55,cy-30),(40,cy-20),(55,cy-10),(40,cy),(55,cy+10),(40,cy+20),(55,cy+30),(80,cy+30))
  path(*[(-55+(15 if i%2 else 0),-80+i*10) for i in range(17)])
 elif typ in ['JACK','MAINS']:
  nums=['T','R','S'] if typ=='JACK' else ['L','N','PE']
  path((-30,-70),(35,-70),(35,70),(-30,70),(-30,-70))
  for n,y in zip(nums,[-45,0,45]):pin(n,65,y,'R');path((50,y),(10,y),(3,y-7),(-4,y));texts.append((n,-23,y-7,11))
 elif typ in ['TP','CHASSIS']:
  pin('1',0,30,'D');path((0,15),(0,0));path(*[(8*math.cos(i*math.pi/8),8*math.sin(i*math.pi/8)) for i in range(17)])
 else:raise ValueError(typ)
 if orient=='V':
  shapes=[[( -y,x) for x,y in points] for points in shapes]
  pins={n:(-y,x,{'L':'U','R':'D','U':'R','D':'L'}[s]) for n,(x,y,s) in pins.items()};texts=[(v,-y,x,z) for v,x,y,z in texts]
 coords=[p for line in shapes for p in line]+[(x,y) for x,y,_ in pins.values()]
 d.add('PART','P',BBOX=[min(x for x,y in coords)-4,min(y for x,y in coords)-4,max(x for x,y in coords)+4,max(y for x,y in coords)+4],title='P')
 for i,line in enumerate(shapes):d.poly('s'+str(i),line,'P')
 for i,(v,x,y,z) in enumerate(texts):d.text('t'+str(i),v,x,y,z,'#5B2323','P')
 for n,(x,y,side) in pins.items():
  pid='p'+n;d.add('PIN',pid,partId='P',x=x,y=y,length=15,rotation={'L':0,'R':180,'U':270,'D':90}[side],display=True,pinShape='NONE')
  for k,v in [('Pin Number',n),('Pin Name',n),('Pin Type','Passive')]:d.attr(pid+k,pid,k,v)
  if typ in ['NPN','MOS']:d.text('no'+n,n,x+5,y-5,9,'#5B2323','P')
 d.add('META','META',title='6H30_'+key,docType=2);DOCS.append(d)
 dd=Doc('DEVICE','dev'+key);dd.add('META','META',title='6H30_'+key,attributes={'Symbol':uid(key),'Designator':'X?','Name':typ,'Add into BOM':'yes','Convert to PCB':'no','Footprint':''});DOCS.append(dd)
 SYMS[key]=pins;return key
P={};BLOCKS=[]
def block(title,ox,oy,w,h):BLOCKS.append((title,ox,oy,w,h));return ox,oy
origin=(0,0)
def place(alias,x,y,o='H'):
 c=C[alias];t=c['type'];t='Z' if t=='D' and 'zener' in c['value'] else 'F' if t=='LINK' and alias.startswith('F') else t
 b=binding(c)
 if b:
  key='LIB:'+b['key']+o;LIBKEYS.add(b['key']);pincoords={}
  for pn in b['pins']:
   sem=next(n for n,actual in b['mapping'].items() if actual==pn['number'])
   px,py=pn['x'],pn['y'];side={0:'L',90:'D',180:'R',270:'U'}[pn['rotation']%360]
   if o=='V':px,py=-py,px;side={'L':'U','R':'D','U':'R','D':'L'}[side]
   pincoords[sem]=(px,py,side)
  SYMS[key]=pincoords;BINDINGS[alias]=b
 else:key=symbol(t,o)
 P[alias]=dict(comp=c,x=x+origin[0],y=y+origin[1],sym=key,orient=o)
# Input / controls, real mechanically paired switch and potentiometer.
origin=block('01  INPUT / HIGH 0 dB - LOW -20 dB / VOLUME',40,130,900,780)
for a,x,y,o in [('J1',90,180,'H'),('SW1',360,250,'H'),('RV1',670,270,'H'),('RATTL',240,430,'H'),('RSHL',360,480,'V'),('RATTR',240,610,'H'),('RSHR',360,660,'V'),('J2',680,590,'H'),('RHPL',520,530,'V'),('RHPR',520,680,'V')]:place(a,x,y,o)
# WCF tube geometry deliberately follows signal flow and vertical DC stack.
for ch,num,xx in [('L',1,980),('R',2,2570)]:
 origin=block('0'+str(num+1)+'  '+ch+' CHANNEL / 6H30Pi WHITE CATHODE FOLLOWER',xx,130,1530,780)
 for a,x,y,o in [('V'+str(num),720,350,'H'),('CIN'+ch,170,240,'H'),('RGS'+ch,470,240,'H'),('RS'+ch,720,100,'V'),('CF'+ch,240,430,'H'),('RGL'+ch,470,450,'H'),('RLEAK'+ch,360,560,'V'),('RK'+ch,740,630,'V'),('CK'+ch,880,630,'V'),('CO'+ch,1010,350,'H'),('RDC'+ch,940,480,'V'),('RBL'+ch,1150,480,'V'),('K'+str(num),1310,350,'H'),('RB1'+ch,120,100,'V'),('RB2'+ch,120,640,'V'),('CB'+ch,240,640,'V'),('RG'+ch,360,170,'V'),('TP'+ch+'MID',930,275,'H'),('TP'+ch+'K',1050,620,'H'),('TP'+ch+'OUT',1150,275,'H')]:place(a,x,y,o)
origin=block('04  220 VAC / ISOLATION / HV RECTIFIER',40,960,1320,730)
for a,x,y,o in [('J3',85,170,'H'),('F1',260,125,'H'),('SW2',470,160,'H'),('T1',720,310,'H'),('CH1',100,370,'H'),('LK1',260,420,'H'),('F2',990,170,'H'),('DH1',1090,260,'H'),('DH2',1090,370,'H'),('DH3',900,480,'H'),('DH4',1100,480,'H'),('CHV1',480,590,'V'),('RHV',720,550,'H'),('CHV2',960,590,'V'),('RDIS1',600,590,'V'),('RDIS2',1100,590,'V')]:place(a,x,y,o)
origin=block('05  B+ 160 V / DISCRETE REGULATOR',1410,960,1250,730)
for a,x,y,o in [('QHV',510,190,'H'),('RHG',270,150,'V'),('DGS',390,320,'H'),('RIS',700,300,'H'),('QIL',690,480,'H'),('QERR',450,500,'H'),('RHU',990,390,'V'),('RHL',990,570,'V'),('RHZ',110,390,'V'),('DZHV',200,570,'V'),('CZHV',320,570,'V'),('CCHV',790,560,'H'),('CBPLUS',1090,200,'V'),('RDIS3',980,200,'V'),('TPB',1140,90,'H')]:place(a,x,y,o)
origin=block('06  6.3 V DC HEATER / FLOATING AT +38 V',2710,960,1390,730)
for a,x,y,o in [('F3',100,130,'H'),('DF1',290,150,'H'),('DF2',290,260,'H'),('DF3',100,370,'H'),('DF4',290,370,'H'),('CHF',520,280,'V'),('U1',780,200,'H'),('RH1',880,350,'V'),('RH2',880,510,'V'),('CHOUT',1110,310,'V'),('CHADJ',1010,510,'V'),('DHREV',780,100,'H'),('DADJ',1170,500,'H'),('REL1',450,510,'V'),('REL2',590,600,'V'),('CEL',730,600,'V')]:place(a,x,y,o)
origin=block('07  AUXILIARY 12 V',40,1740,900,800)
for a,x,y,o in [('DA1',190,130,'H'),('DA2',190,260,'H'),('DA3',190,390,'H'),('DA4',190,520,'H'),('CAUX',390,230,'V'),('RAZ',540,160,'V'),('DAZ',540,390,'V'),('QAUX',710,230,'H'),('CA12',700,490,'V'),('RA12',700,650,'V')]:place(a,x,y,o)
origin=block('08  DELAY / AC LOSS / RELAY / DC REFERENCES',980,1740,1140,800)
for a,x,y,o in [('RT',110,140,'V'),('CT',110,340,'V'),('DZT',270,240,'H'),('RTB',450,240,'H'),('QT1',610,240,'H'),('QT2',630,430,'H'),('RBE',480,430,'V'),('DFLY',800,140,'V'),('DZFLY',920,140,'V'),('DACS',120,560,'H'),('CACS',260,660,'V'),('RACS',380,660,'V'),('RACB',510,560,'H'),('QAC',680,590,'H'),('RKILL',890,470,'V'),('QKILL',880,660,'H'),('RR1',1040,240,'V'),('RR2',1040,380,'V'),('RR3',1040,520,'V'),('RR4',1040,660,'V')]:place(a,x,y,o)
for ch,xx in [('L',2170),('R',3170)]:
 origin=block(('09' if ch=='L' else '10')+'  '+ch+' DC WINDOW DETECTOR',xx,1740,930,800)
 for a,x,y,o in [('RDS1',110,140,'V'),('RDS2',270,140,'V'),('CDS',270,310,'V'),('DSP',460,100,'H'),('DSN',650,100,'H'),('QPS',230,440,'H'),('QPR',430,440,'H'),('QNS',600,440,'H'),('QNR',800,440,'H'),('RTP',330,620,'V'),('RTN',710,620,'V'),('RCP',120,300,'V'),('RCN',810,300,'V'),('DTRP',130,720,'H'),('DTRN',560,720,'H'),('DBEPS',140,540,'H'),('DBEPR',440,540,'H'),('DBENS',610,210,'H'),('DBENR',800,210,'H')]:place(a+ch,x,y,o)
assert set(P)==set(C),(set(C)-set(P),set(P)-set(C))
# The only automatic direct links are short, aligned, facing pins with no other pin in between.
def main():
 page=Doc('SCH_PAGE','ALL');page.add('CANVAS','CANVAS',originX=0,originY=0);page.add('META','META',title='01_COMPLETE_STEREO_AMPLIFIER',schematic=uid('SCH'),zIndex=1)
 page.text('title','TWO 6H30Pi STEREO OTL - COMPLETE SCHEMATIC',45,50,32)
 page.text('subtitle','HIGH: bypass | LOW: -20 dB | 220 V / 50 Hz | Candidate v0.1 electrical design, drawing revision v0.3',45,85,18)
 page.text('status','NOT RELEASED FOR REAL HEADPHONES: protection, ripple and tolerance acceptance FAILED. No PCB / no physical test.',45,113,15,'#A02B20')
 for i,(title,x,y,w,h) in enumerate(BLOCKS):
  page.poly('frame'+str(i),[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)])
  page.text('block'+str(i),title,x+20,y+33,19)
 endpoint={};regions={}
 for a,p in P.items():
  c=p['comp'];ref=c['ref'];x=p['x'];y=p['y'];key=p['sym'];b=BINDINGS.get(a);page.add('COMPONENT',ref,partId=b['part'] if b else 'P',x=x,y=y,rotation=270 if b and p['orient']=='V' else 0,isMirror=False,attrs={},zIndex=3)
  labely=y-32 if c['type'] in ['R','C','D','LINK'] and key.endswith('H') else y-64 if c['type'] not in ['TUBE','TX','POT','GAIN','RELAY','SW','JACK','MAINS'] else y-215 if c['type']=='TUBE' else y-110
  labelx=x-30 if key.endswith('H') else x+14
  val=c['value']
  if c['type']=='C':val+=' / '+c['rating'].split(',')[0].split(' ')[0]
  elif c['type']=='R':val+=' / '+c['rating'].split(',')[0].split(' ')[0]
  props=dict(b['properties']) if b else {'Device':uid('dev'+key),'Symbol':uid(key),'Footprint':'','Convert to PCB':'no'}
  if b and b['device']:props['Device']=b['device']
  props.update({'Designator':ref,'Name':val,'Add into BOM':'yes','Role':a,'Required Rating':c['rating']})
  if b:props.update({'Library UUID':b['item']['libraryUuid'],'Library Source':b['kind']+':'+b['item']['uuid']})
  for k,v in props.items():page.attr(ref+k,ref,k,v,labelx,labely+(15 if k=='Name' else 0),k in ['Designator','Name'],12)
  for n,(dx,dy,side) in SYMS[key].items():endpoint[(a,n)]=dict(x=x+dx,y=y+dy,side=side,net=c['pins'][n],ref=ref,library_pin=b['mapping'][n] if b else n)
  regions[a]=next(i for i,(_,xx,yy,w,h) in enumerate(BLOCKS) if xx<x<xx+w and yy<y<yy+h)
 used=set();ports=[];wirecount=0;direct=0
 def wire(net,points):
  nonlocal wirecount
  wirecount+=1;i='w'+str(wirecount);page.add('WIRE',i,zIndex=2);page.attr(i+'net',i,'NET',net)
  for j,((x1,y1),(x2,y2)) in enumerate(zip(points,points[1:])):page.add('LINE',i+'s'+str(j),lineGroup=i,startX=x1,startY=y1,endX=x2,endY=y2,strokeColor='#167049',strokeWidth=1,zIndex=2)
 def pos(k):e=endpoint[k];return e['x'],e['y']
 # WCF upper cathode/lower plate node and series input path are physically drawn.
 for ch,n in [('L',1),('R',2)]:
  a=('V'+str(n),'8');b=('V'+str(n),'1');pa=pos(a);pb=pos(b);route=[pa,(pa[0]+45,pa[1]),(pa[0]+45,pb[1]),pb]
  wire(ch+'_MID',route);used.update([a,b]);ports.append(dict(net=ch+'_MID',x=pa[0]+45,y=pa[1],side='R'))
  for aa,bb in [(('CIN'+ch,'2'),('RGS'+ch,'1')),(('RGS'+ch,'2'),('V'+str(n),'7')),(('RGL'+ch,'2'),('V'+str(n),'2'))]:
   ea=endpoint[aa];eb=endpoint[bb];assert ea['net']==eb['net'];p1=pos(aa);p2=pos(bb);wire(ea['net'],[p1,p2] if p1[1]==p2[1] else [p1,(p2[0]-30,p1[1]),(p2[0]-30,p2[1]),p2]);used.update([aa,bb]);ports.append(dict(net=ea['net'],x=p1[0]+25,y=p1[1],side='D'));direct+=1
 # short straight links inside blocks (exact shared electrical net only)
 for ka,a in endpoint.items():
  if ka in used:continue
  candidates=[]
  for kb,b in endpoint.items():
   if kb==ka or kb in used or a['net']!=b['net'] or regions[ka[0]]!=regions[kb[0]]:continue
   dx=b['x']-a['x'];dy=b['y']-a['y']
   facing=(dy==0 and 0<dx<=210 and a['side']=='R' and b['side']=='L') or (dx==0 and 0<dy<=160 and a['side']=='D' and b['side']=='U')
   if facing:candidates.append((abs(dx)+abs(dy),kb))
  if candidates:
   _,kb=min(candidates);wire(a['net'],[pos(ka),pos(kb)]);used.update([ka,kb]);direct+=1;ports.append(dict(net=a['net'],x=(a['x']+endpoint[kb]['x'])/2,y=(a['y']+endpoint[kb]['y'])/2,side='D'))
 for k,e in endpoint.items():
  if k in used:continue
  dx,dy={'L':(-35,0),'R':(35,0),'U':(0,-35),'D':(0,35)}[e['side']];p=(e['x']+dx,e['y']+dy);wire(e['net'],[pos(k),p]);ports.append(dict(net=e['net'],x=p[0],y=p[1],side=e['side']))
 page.text('tube-note','V1 / V2 socket BOTTOM wiring view: 4 and 5 HEATER, 9 SCREEN. Same NET name = connected. HMINUS is elevated, not AGND.',50,2590,17)
 page.text('ratings','Nominal per channel: B+ 160 V, MID ~82 V, Iq ~36.5 mA. Upper/lower plate dissipation ~2.7 / 2.9 W. See rated BOM and failed-acceptance report.',50,2620,16)
 sch=Doc('SCH','SCH');sch.add('META','META',title='6H30Pi_COMPLETE',board='')
 cfg=Doc('CONFIG','CONFIG');cfg.rows[0][1]['uuid']='CONFIG';cfg.add('UNIVERSAL','UNIVERSAL',allowLibRename=True,defaultNetName=True,wireMultipleNet=True,netFlagCrossLayerConnection=True,netLabelCrossPageConnection=True)
 # Real Netport-BI component records, not free text pretending to be electrical labels.
 net=SELECTED['NET'];ni=net['item'];part=net['pins'][0]['part']
 for j,port in enumerate(ports):
  i='NP'+str(j);x,y=port['x'],port['y'];side=port['side']
  angle={'R':0,'L':180,'D':270,'U':90}[side]
  page.add('COMPONENT',i,partId=part,x=x,y=y,rotation=angle,isMirror=False,attrs={},zIndex=3)
  for k,v in [('Symbol',ni['uuid']),('Name',port['net']),('NET',port['net']),('Add into BOM','no'),('Convert to PCB','no')]:
   page.attr(i+k,i,k,v,x+8,y-8,k=='Name',10)
 docs=DOCS+[sch,page,cfg]
 libdocs=documents(LIBKEYS)
 libsource='|\n'.join('|\n'.join(json.dumps(h,separators=(',',':'))+'||'+json.dumps(v,separators=(',',':')) for h,v in [d['head'],*d['rows'].values()]) for d in libdocs.values())
 source=libsource+'|\n'+'|\n'.join(d.dump() for d in docs)
 provenance={a:{'ref':P[a]['comp']['ref'],'kind':b['kind'],'name':b['item']['name'],'library_uuid':b['item']['libraryUuid'],'device_uuid':b['device'],'symbol_uuid':b['symbol'],'supplier_id':b['item'].get('supplierId'),'manufacturer':b['item'].get('manufacturer'),'pin_map':b['mapping'],'pins':b['pins'],'properties':b['properties']} for a,b in BINDINGS.items()}
 (OUT/'library-bindings.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
 (OUT/'6H30Pi-OneSheet.epru').write_text(source)
 with zipfile.ZipFile(OUT/'6H30Pi-OneSheet.epro2','w',zipfile.ZIP_DEFLATED) as z:z.writestr('project2.json',json.dumps({'title':NAME,'cbb_project':False,'editorVersion':'3.2.186','tags':'[]'}));z.writestr('6H30Pi-OneSheet.epru',source)
 (OUT/'net-ports.json').write_text(json.dumps(ports,indent=2)+'\n')
 (OUT/'drawing-manifest.json').write_text(json.dumps({'name':NAME,'schematic_uuid':uid('SCH'),'page_uuid':uid('ALL'),'components':{a:{'ref':p['comp']['ref'],'x':p['x'],'y':p['y'],'symbol':p['sym']} for a,p in P.items()},'pins':[dict(alias=a,pin=n,**e) for (a,n),e in endpoint.items()],'direct_links':direct,'marker_count':len(ports),'component_count':len(P)},indent=2)+'\n')
 print(NAME,len(P),'components, 1 sheet,',direct,'direct links,',len(ports),'NET marker placements')
if __name__=='__main__':main()
