#!/usr/bin/env python3
"""Single connection manifest -> coordinate-free BoardSpec and rated BOM.
Project-authored symbols use official tube/semiconductor terminal maps.
Panel items/transformer/relay use FUNCTIONAL terminals, not guessed land patterns.
"""
from pathlib import Path
import json,csv,collections,yaml
ROOT=Path(__file__).resolve().parents[1]
S={
 'tube':'https://shop.ehx.com/catalog/tubes-specs/6H30Pi-EB.pdf',
 'sovtek':'https://shop.ehx.com/catalog/addimages/6h30pi-sovtek.pdf',
 'mos':'https://www.vishay.com/docs/91059/91059.pdf',
 'npn':'https://www.onsemi.com/download/data-sheet/pdf/mpsa42-d.pdf',
 'ldo':'https://www.ti.com/lit/ds/symlink/lm1084.pdf',
 'relay':'https://www.pickeringrelay.com/wp-content/uploads/pdfs/104-high-voltage-sil-reed-relays.pdf',
 'rectifier':'https://www.hammfg.com/es/electronics/transformers/rectifier?referer=968',
 'project':'Project-defined functional terminals; package/purchasing verification required before build'}
T={
'R': [('1','1'),('2','2')], 'C':[('1','+'),('2','-')],
'D':[('A','A'),('K','K')], 'NPN':[('1','E'),('2','B'),('3','C')],
'MOS':[('1','G'),('2','D'),('3','S')], 'LDO':[('1','ADJ'),('2','OUT'),('3','IN')],
'TUBE':[('1','P2'),('2','G2'),('3','K2'),('4','H'),('5','H'),('6','P1'),('7','G1'),('8','K1'),('9','SCREEN')],
'JACK':[('T','TIP_L'),('R','RING_R'),('S','SLEEVE')],
'GAIN':[('LC','L_COMMON'),('LH','L_HIGH'),('LL','L_LOW'),('RC','R_COMMON'),('RH','R_HIGH'),('RL','R_LOW')],
'POT':[('LT','L_TOP'),('LW','L_WIPER'),('LB','L_BOTTOM'),('RT','R_TOP'),('RW','R_WIPER'),('RB','R_BOTTOM')],
'RELAY':[('CA','COIL_A'),('CB','COIL_B'),('A','CONTACT_A'),('B','CONTACT_B')],
'TX':[('P1','PRI_L'),('P2','PRI_N'),('H1','HV_A'),('H2','HV_B'),('F1','HTR_A'),('F2','HTR_B'),('A1','AUX_A'),('A2','AUX_B'),('SH','SCREEN')],
'MAINS':[('L','LINE'),('N','NEUTRAL'),('PE','PE')],
'SW':[('L1','L_IN'),('L2','L_OUT'),('N1','N_IN'),('N2','N_OUT')],
'LINK':[('1','1'),('2','2')], 'TP':[('1','TEST')], 'CHASSIS':[('1','PE_STUD')]
}
C=[]
def add(ref,typ,val,nets,page,rating='',source='project',note=''):
 assert len(nets)==len(T[typ]),(ref,typ,nets)
 C.append(dict(ref=ref,type=typ,value=val,pins={n:net for (n,_),net in zip(T[typ],nets)},page=page,rating=rating,source=S[source],note=note))
def r(ref,v,a,b,p,w='.25W, 1%, >=250V'):add(ref,'R',v,[a,b],p,w)
def c(ref,v,a,b,p,rating='250V, film 5%'):add(ref,'C',v,[a,b],p,rating,note='Pin 1 positive for electrolytic; film non-polar')
def d(ref,v,a,k,p,rating='100V, 150mA'):add(ref,'D',v,[a,k],p,rating)
def q(ref,e,b,col,p):add(ref,'NPN','MPSA42',[e,b,col],p,'300V VCEO, 0.5A; E/B/C=1/2/3','npn')
# Audio interface and two-position double-pole selector.
p='01_Input_and_controls'
add('J1','JACK','3.5mm stereo INPUT',['IN_L','IN_R','AGND'],p,'Insulated chassis jack')
add('SW1','GAIN','DPDT HIGH / LOW',['SEL_L','IN_L','ATT_L','SEL_R','IN_R','ATT_R'],p,'Break before make; two poles mechanically linked',note='High connects C-H; Low connects C-L. Turn volume down before switching.')
add('RV1','POT','Dual 10k log',['SEL_L','WIP_L','AGND','SEL_R','WIP_R','AGND'],p,'2 gangs; >=0.1W; gang tracking must be measured')
add('J2','JACK','3.5mm stereo OUTPUT',['HP_L','HP_R','AGND'],p,'Insulated chassis jack; no balanced output')
for ch in ['L','R']:
 r('RATT'+ch,'8.2k','IN_'+ch,'ATT_'+ch,p)
 r('RSH'+ch,'1k','ATT_'+ch,'AGND',p)
 r('RHP'+ch,'100k','HP_'+ch,'AGND',p)
# Audio. Each tube shares heater/screen but all six electrode pins individually connected.
for ch,ti in [('L',1),('R',2)]:
 p=f'0{ti+1}_WCF_{ch}';n=lambda x:f'{ch}_{x}'
 add('V'+str(ti),'TUBE','6H30Pi-EB',[n('MID'),n('GL'),n('K'),'HPLUS','HMINUS',n('PA'),n('GU'),n('MID'),'AGND'],p,'Pa <=4W each; Ia <=50mA continuous; |Vhk| <=100V conservative','tube','Socket BOTTOM / wiring view. 4,5 heater; 9 SCREEN, never heater.')
 c('CIN'+ch,'4.7u','WIP_'+ch,n('GI'),p)
 r('RB1'+ch,'100k','BPLUS',n('BIAS'),p)
 r('RB2'+ch,'100k',n('BIAS'),'AGND',p)
 c('CB'+ch,'47u',n('BIAS'),'AGND',p,'160V electrolytic, +/-20%')
 r('RG'+ch,'47k',n('BIAS'),n('GI'),p)
 r('RGS'+ch,'100',n('GI'),n('GU'),p)
 r('RS'+ch,'127', 'BPLUS',n('PA'),p,'1W, 1%, metal film; nominal 0.17W')
 c('CF'+ch,'4.7u',n('PA'),n('GB'),p)
 r('RGL'+ch,'100',n('GB'),n('GL'),p)
 r('RLEAK'+ch,'100k',n('GB'),'AGND',p)
 r('RK'+ch,'68',n('K'),'AGND',p,'1W, 1%; nominal 0.091W')
 c('CK'+ch,'2200u',n('K'),'AGND',p,'16V electrolytic +/-20%')
 c('CO'+ch,'1000u',n('MID'),n('OUT'),p,'250V electrolytic +/-20%; ESR target <=0.15 ohm @1k; leakage MUST be measured')
 r('RDC'+ch,'100k',n('MID'),'AGND',p,'2W flameproof; defined discharge of output coupling capacitor')
 r('RBL'+ch,'10k',n('OUT'),'AGND',p,'2W flameproof; 0.67W at 82V fault')
 add('K'+str(ti),'RELAY','104-1-A-12/1',['AUX12','COIL_LO',n('OUT'),'HP_'+ch],p,'500VDC switching, 0.5A/10W maximum; no internal diode','relay','FUNCTIONAL pin labels. Confirm ordered package pinout. Contact ESR budget 0.15 ohm. Hard capacitor short exceeds contact current rating: NOT qualified.')
 for part,net in [('MID',n('MID')),('K',n('K')),('OUT',n('OUT'))]:add('TP'+ch+part,'TP',part,[net],p,'Insulated test point >=250V')
# Mains isolated transformer & HV rectifier.
p='04_Mains_and_rectifier'
add('J3','MAINS','IEC C14 fused inlet',['MAINS_L','MAINS_N','PE'],p,'250VAC certified; touch-safe enclosure')
add('F1','LINK','T630mA H 250V',['MAINS_L','FUSED_L'],p,'High breaking capacity; inrush validation required')
add('SW2','SW','DPST mains switch',['FUSED_L','PRI_L','MAINS_N','PRI_N'],p,'250VAC >=2A certified')
add('T1','TX','220V : 150V / 9.5V / 12V',['PRI_L','PRI_N','HV_A','HV_B','HTR_A','HTR_B','AUX_A','AUX_B','PE'],p,'>=100VA; 150VAC/0.25A + 9.5VAC/5A + 12VAC/0.3A; reinforced isolation; thermal fuse','rectifier','Custom transformer winding TERMINALS; no autotransformer. Ratings at load. Electrostatic screen bonded to PE.')
add('CH1','CHASSIS','Dedicated PE stud',['PE'],p,'Bolted protective-earth bond; never switched/fused')
add('LK1','LINK','Single star bond',['PE','AGND'],p,'Short chassis-to-signal-ground bond at single point')
add('F2','LINK','T315mA H 250V',['HV_A','HV_AF'],p,'HV winding fuse')
for num,a,k in [(1,'HV_AF','HV_RAW'),(2,'HV_B','HV_RAW'),(3,'AGND','HV_AF'),(4,'AGND','HV_B')]:d('DH'+str(num),'UF4007',a,k,p,'1000V, 1A')
c('CHV1','220u','HV_RAW','AGND',p,'350V +/-20%; ripple >=0.3Arms @100Hz')
r('RHV','22','HV_RAW','HV_IN',p,'5W pulse-rated flameproof')
c('CHV2','220u','HV_IN','AGND',p,'350V +/-20%; ripple >=0.3Arms @100Hz')
r('RDIS1','100k','HV_RAW','AGND',p,'2W, >=350V, flameproof')
r('RDIS2','100k','HV_IN','AGND',p,'2W, >=350V, flameproof')
# Regulator.
p='05_HV_regulator'
add('QHV','MOS','IRF820',['HV_GATE','HV_IN','HV_SOURCE'],p,'500V; heatsink <=8C/W; electrically insulated tab (D)','mos','Linear DC SOA not signed off; transient short dissipation gate remains open.')
r('RHG','47k','HV_IN','HV_GATE',p,'2W, >=350V')
d('DGS','12V zener','HV_SOURCE','HV_GATE',p,'1W')
r('RIS','4.7','HV_SOURCE','BPLUS',p,'1W; current limit ~0.13A, untrimmed')
q('QIL','BPLUS','HV_SOURCE','HV_GATE',p)
q('QERR','HV_ZREF','HV_FB','HV_GATE',p)
r('RHU','221k','BPLUS','HV_FB',p)
r('RHL','10k','HV_FB','AGND',p)
r('RHZ','82k','HV_IN','HV_ZREF',p,'2W, >=350V')
d('DZHV','6.2V zener','AGND','HV_ZREF',p,'0.5W; operating current ~2mA; tolerance 2% or better')
c('CZHV','47u','HV_ZREF','AGND',p,'25V electrolytic')
c('CCHV','10n','HV_GATE','HV_FB',p,'250V film; loop stability not qualified')
c('CBPLUS','100u','BPLUS','AGND',p,'250V electrolytic')
r('RDIS3','100k','BPLUS','AGND',p,'2W flameproof')
add('TPB','TP','B+ 160V nominal',['BPLUS'],p,'Insulated HV point')
# heater
p='06_Heater_and_aux'
add('F3','LINK','T5A 250V',['HTR_A','HTR_AF'],p,'Heater winding fuse; inrush test required')
for num,a,k in [(1,'HTR_AF','HRAW'),(2,'HTR_B','HRAW'),(3,'HMINUS','HTR_AF'),(4,'HMINUS','HTR_B')]:d('DF'+str(num),'MBR1045',a,k,p,'45V, 10A; insulated mounting as applicable')
c('CHF','15000u','HRAW','HMINUS',p,'25V +/-20%; ripple >=4Arms @100Hz')
add('U1','LDO','LM1084IT-ADJ',['HADJ','HPLUS','HRAW'],p,'5A; heat sink <=1.5C/W; tab=OUT, insulate from chassis','ldo')
r('RH1','121','HPLUS','HADJ',p)
r('RH2','487','HADJ','HMINUS',p)
c('CHOUT','220u','HPLUS','HMINUS',p,'16V aluminum, ESR 0.2..1 ohm; regulator stability verification required')
c('CHADJ','10u','HADJ','HMINUS',p,'16V electrolytic')
d('DHREV','1N5404','HPLUS','HRAW',p,'400V 3A output-to-input reverse protection')
d('DADJ','1N4148','HADJ','HPLUS',p)
r('REL1','150k','BPLUS','HMINUS',p,'0.5W 1%')
r('REL2','47k','HMINUS','AGND',p)
c('CEL','47u','HMINUS','AGND',p,'100V electrolytic')
p='06b_Auxiliary_supply'
for num,a,k in [(1,'AUX_A','AUX_RAW'),(2,'AUX_B','AUX_RAW'),(3,'AGND','AUX_A'),(4,'AGND','AUX_B')]:d('DA'+str(num),'1N4007',a,k,p,'1000V 1A')
c('CAUX','1000u','AUX_RAW','AGND',p,'35V electrolytic')
r('RAZ','470','AUX_RAW','AUX_Z',p,'0.5W')
d('DAZ','13V zener','AGND','AUX_Z',p,'0.5W 2%')
q('QAUX','AUX12','AUX_Z','AUX_RAW',p)
c('CA12','220u','AUX12','AGND',p,'25V electrolytic')
r('RA12','4.7k','AUX12','AGND',p)
# Delay/AC fail: AC detection uses bridge input half waves from AUX_A wrt AGND.
p='07_Delay_and_relay_driver'
r('RT','330k','AUX12','TIMER',p)
c('CT','100u','TIMER','AGND',p,'25V low leakage; +/-20% directly changes delay')
d('DZT','5.1V zener','TBASE','TIMER',p,'0.5W')
r('RTB','1k','TBASE','QB1',p)
q('QT1','QB2','QB1','COIL_LO',p);q('QT2','AGND','QB2','COIL_LO',p)
r('RBE','100k','QB2','AGND',p)
# Fast coil flyback clamp (one shared clamp; no diode inside selected relays)
d('DFLY','1N4148','COIL_LO','FLY_Z',p)
d('DZFLY','24V zener','AUX12','FLY_Z',p,'1W pulse-rated; verify coil voltage and release time')
d('DACS','1N4148','AUX_A','AC_PRESENT',p)
c('CACS','470n','AC_PRESENT','AGND',p,'50V film')
r('RACS','10k','AC_PRESENT','AGND',p)
r('RACB','47k','AC_PRESENT','AC_B',p)
q('QAC','AGND','AC_B','KILL_B',p)
r('RKILL','10k','AUX12','KILL_B',p)
q('QKILL','AGND','KILL_B','TIMER',p)
# Comparator reference ladder shared L/R.
r('RR1','2.3k','AUX12','REFHI',p)
r('RR2','100','REFHI','REFMID',p)
r('RR3','100','REFMID','REFLO',p)
r('RR4','2.3k','REFLO','AGND',p)
for ch,idx in [('L',8),('R',9)]:
 p=f'0{idx}_DC_monitor_{ch}';n=lambda x:f'{ch}_{x}'
 r('RDS1'+ch,'100k','AUX12',n('SENSE'),p)
 r('RDS2'+ch,'100k',n('OUT'),n('SENSE'),p,'0.5W >=250V')
 c('CDS'+ch,'1u',n('SENSE'),'REFMID',p,'250V film, non-polar')
 d('DSP'+ch,'1N4148',n('SENSE'),'AUX12',p)
 d('DSN'+ch,'1N4148','AGND',n('SENSE'),p)
 q('QPS'+ch,n('TAILP'),n('SENSE'),n('POSC'),p)
 q('QPR'+ch,n('TAILP'),'REFHI','AUX12',p)
 q('QNS'+ch,n('TAILN'),n('SENSE'),'AUX12',p)
 q('QNR'+ch,n('TAILN'),'REFLO',n('NEGC'),p)
 r('RTP'+ch,'4.7k',n('TAILP'),'AGND',p)
 r('RTN'+ch,'4.7k',n('TAILN'),'AGND',p)
 r('RCP'+ch,'10k','AUX12',n('POSC'),p)
 r('RCN'+ch,'10k','AUX12',n('NEGC'),p)
 d('DTRP'+ch,'1N4148','TIMER',n('POSC'),p)
 d('DTRN'+ch,'1N4148','TIMER',n('NEGC'),p)
 for tag,em,base in [('PS','TAILP','SENSE'),('PR','TAILP','REFHI'),('NS','TAILN','SENSE'),('NR','TAILN','REFLO')]:
  d('DBE'+tag+ch,'1N4148',n(em),n(base) if base=='SENSE' else base,p)
# Write manifest / BoardSpec.
def main():
 counts=collections.Counter()
 for comp in C:
  comp['alias']=comp['ref']; typ=comp['type']
  pref={'R':'R','C':'C','D':'D','NPN':'Q','MOS':'Q','LDO':'U','TUBE':'V','JACK':'J','GAIN':'SW','POT':'RV','RELAY':'K','TX':'T','MAINS':'J','SW':'SW','LINK':'F' if comp['alias'].startswith('F') else 'LK','TP':'TP','CHASSIS':'CH'}[typ]
  counts[pref]+=1;comp['ref']=pref+str(counts[pref])
 data={'name':'QuickPCB_6H30Pi_OTL_IEM_v01_review2','revision':'0.1-candidate','status':'NOT QUALIFIED FOR REAL HEADPHONES','types':T,'components':C,'sources':S}
 (ROOT/'circuit.json').write_text(json.dumps(data,indent=2)+'\n')
 defs={}
 for typ,pins in T.items():
  defs['project:'+typ]={'kind':'physical','description':'Project-authored schematic symbol; '+('official electrode pinout' if typ=='TUBE' else 'see circuit.json/BOM for terminal authority'),'pins':[{'number':n,'name':name,'type':'passive'} for n,name in pins], 'source':{'provider':'project'},'review':{'status':'project_reviewed','pin_type_authority':'project_library','note':'Functional terminals for panel items; no PCB footprint claimed.'}}
 nets=collections.defaultdict(list)
 for comp in C:
  for pin,net in comp['pins'].items():nets[net].append(comp['ref']+'.#'+pin)
 spec={'spec':'board-spec/v0.1','project':{'name':data['name'],'version':'0.1','description':data['status']},'definitions':defs,'instances':{x['ref']:{'part':'project:'+x['type'],'value':x['value'],'properties':{'rating':x['rating'],'source':x['source'],'sheet':x['page'],'role':x['alias']}} for x in C},'connections':[{'net':n,'endpoints':ep} for n,ep in nets.items()]}
 (ROOT/'boardspec.yaml').write_text(yaml.safe_dump(spec,sort_keys=False,allow_unicode=True))
 with (ROOT/'BOM.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=['ref','alias','value','type','rating','source','note','page']);w.writeheader();w.writerows({k:v for k,v in x.items() if k!='pins'} for x in C)
 (ROOT/'results/connectivity_expected.json').write_text(json.dumps(dict(nets),indent=2)+'\n')
 print(f'{len(C)} components, {len(nets)} nets, {len(set(x["page"] for x in C))} sheets')
if __name__=='__main__':main()
