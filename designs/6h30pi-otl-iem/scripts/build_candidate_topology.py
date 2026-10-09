#!/usr/bin/env python3
"""Fresh physical-pin candidate topology from the locked library; not qualified hardware."""
import json,csv,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=json.loads((R/'parts.lock.json').read_text())['parts']
EX=json.loads((R/'parts.exceptions.json').read_text())['parts']
parts=[];notes=[]
def add(ref,key,pins,x,y,section,value=None,angle=0,note=''):
 if key in P:
  actual={str(p['number']) for p in P[key]['pins']}
  assert set(pins)==actual,(ref,key,actual,set(pins))
 assert ref not in {p['ref'] for p in parts},ref
 parts.append(dict(ref=ref,key=key,pins=pins,x=x,y=y,angle=angle,section=section,value=value,note=note))
def two(ref,key,a,b,x,y,s,value=None,angle=0,note=''):add(ref,key,{'1':a,'2':b},x,y,s,value,angle,note)
def rr(ref,key,a,b,x,y,s,angle=0):two(ref,'r_'+key,a,b,x,y,s,angle=angle)
def cc(ref,key,a,b,x,y,s,angle=0):two(ref,'c_'+key,a,b,x,y,s,angle=angle)
def dd(ref,key,a,k,x,y,s,angle=0):two(ref,key,k,a,x,y,s,angle=angle)
def qn(ref,e,b,c,x,y,s,key='hv_npn'):
 mapping={'1':e,'2':b,'3':c} if key=='hv_npn' else {'1':e,'2':c,'3':b}
 add(ref,key,mapping,x,y,s)
def note(x,y,text):notes.append(dict(x=x,y=y,text=text))
# Inputs. EG2208: common2/5; high1/4; low3/6. Mechanical tabs0 are NC.
s='01 INPUT / GAIN / VOLUME'
add('J1','jack_trs',{'1':'AGND','2':'IN_R','3':'IN_L'},170,310,s)
add('SW1','gain_dpdt',{'1':'IN_L','2':'SEL_L','3':'LOW_L','4':'IN_R','5':'SEL_R','6':'LOW_R','0':None},650,360,s)
for ch,y in [('L',260),('R',510)]:
 rr('RA'+ch,'8k2_025w','IN_'+ch,'LOW_'+ch,400,y,s)
 rr('RB'+ch,'1k_025w','LOW_'+ch,'AGND',510,y+90,s,90)
add('RV1','pot_dual10k_log',{'1':'AGND','2':'WIP_L','3':'SEL_L','4':'AGND','5':'WIP_R','6':'SEL_R'},870,360,s)
note(130,610,'HIGH: direct / LOW: 8.2k + (1k || 10k pot), nominal -20dB')
note(130,640,'RV1 dual 10k log, 1/4=CCW, 2/5=wiper, 3/6=CW')
# Re-derived classic WCF: top cathode joins lower plate; lower cathode self bias.
for ch,x in [('L',1200),('R',2600)]:
 s='02 '+ch+' WHITE CATHODE FOLLOWER'
 add('V'+ch,'tube_6h30pi_eb',{'1':ch+'_MID','2':ch+'_GL','3':ch+'_K','4':'HPLUS','5':'HMINUS','6':ch+'_PA','7':ch+'_GU','8':ch+'_MID','9':'AGND'},x+640,420,s)
 # A at420; B at700; H at915 are drawing units of the same physical bottle.
 cc('CI'+ch,'signal_4u7film','WIP_'+ch,ch+'_GI',x+160,420,s)
 rr('RGT'+ch,'100_025w',ch+'_GI',ch+'_GU',x+420,420,s)
 rr('RBU'+ch,'100k_025w','BPLUS',ch+'_BIAS',x+90,230,s,90)
 rr('RBD'+ch,'100k_025w',ch+'_BIAS','AGND',x+90,330,s,90)
 cc('CB'+ch,'hv_220u400',ch+'_BIAS','AGND',x+250,285,s,90)
 rr('RGB'+ch,'100k_025w',ch+'_BIAS',ch+'_GI',x+380,285,s,90)
 rr('RS'+ch,'127_1w','BPLUS',ch+'_PA',x+640,230,s,90)
 cc('CF'+ch,'signal_4u7film',ch+'_PA',ch+'_GB',x+380,600,s)
 rr('RGL'+ch,'100_025w',ch+'_GB',ch+'_GL',x+470,700,s)
 rr('RLG'+ch,'100k_025w',ch+'_GB','AGND',x+300,760,s,90)
 rr('RK'+ch,'68_1w',ch+'_K','AGND',x+640,810,s,90)
 cc('CK'+ch,'cathode_2200u25',ch+'_K','AGND',x+770,810,s)
 cc('CO'+ch,'output_1000u250',ch+'_MID',ch+'_OUT',x+875,420,s)
 rr('RD'+ch,'100k_1w',ch+'_MID','AGND',x+810,585,s,90)
 rr('RO1'+ch,'100k_1w',ch+'_OUT','AGND',x+1000,590,s,90)
 rr('RO2'+ch,'100k_1w',ch+'_OUT','AGND',x+1100,590,s,90)
 add('K'+ch,'relay_hv',{'1':ch+'_OUT','4':'HP_'+ch,'2':'AUX12','3':'COIL_LOW'},x+1080,420,s)
 note(x+20,860,'TP '+ch+'_MID: ~80V; '+ch+'_K: ~2.4V; target Iq~35mA (verify)')
 note(x+20,890,'RS 127R / RK 68R 1W; CO 1000u/250V (+ toward tube)')
 note(x+20,990,'6H30Pi bottom-view pinout: 4/5 heater, 9 internal screen. Socket unresolved.')
add('J2','jack_trs',{'1':'AGND','2':'HP_R','3':'HP_L'},4200,430,'03 HEADPHONE OUTPUT')
note(4000,530,'3.5mm TRS: tip=L, ring=R, sleeve=AGND')
note(4000,570,'NO REAL HEADPHONES: candidate fault protection not qualified')
# Mains and isolated custom transformer. Terminal numbers are contract only.
s='04 MAINS / ISOLATION'
add('J3','mains_inlet',{'L':'MAINS_L','N':'MAINS_N','PE':'PE'},150,1350,s)
two('F1','fuse_mains_1a','MAINS_L','FUSED_L',360,1280,s)
add('SW2','mains_switch',{'1':'FUSED_L','1a':'PRI_L','2':'MAINS_N','2a':'PRI_N'},570,1340,s)
add('T1','transformer_contract',{'1':'PRI_L','2':'PRI_N','3':'HV_A','4':'HV_B','5':'HTR_A','6':'HTR_B','7':'AUX_A','8':'AUX_B'},850,1400,s)
note(100,1590,'T1: ISOLATED custom 100VA / 220V50Hz -> 150V0.25A + 9.5V5A + 12V0.3A')
note(100,1620,'T1 1..8 = PROPOSED terminal contract; manufacturer pin drawing REQUIRED')
note(100,1650,'PE: dedicated bolted chassis bond, unswitched, unfused; T1 screen/chassis to PE')
note(100,1680,'AGND / HV return / AUX return meet at one star; PE bond shown by LK1')
# Physical star connection through a rated two-position terminal: explicit short wire.
add('LK1','terminal_2',{'1':'PE','2':'AGND'},410,1490,s,note='Install short bolted bonding strap between terminals1/2; never rely on PCB tracks for PE')
note(100,1730,'LK1: bolt PE and audio star together with dedicated chassis bonding strap; verify continuity')
s='05 HV RECTIFIER / DISCRETE REGULATOR'
two('F2','fuse_hv_500ma','HV_A','HV_AF',1240,1240,s)
for ref,a,k,x,y in [('DH1','HV_AF','HV_RAW',1420,1220),('DH2','HV_B','HV_RAW',1420,1390),('DH3','AGND','HV_AF',1420,1300),('DH4','AGND','HV_B',1420,1470)]:dd(ref,'d_hv_uf4007',a,k,x,y,s)
cc('CHV1','hv_220u400','HV_RAW','AGND',1590,1280,s,90)
rr('RCRC','22_1w','HV_RAW','HV_IN',1710,1170,s)
cc('CHV2','hv_220u400','HV_IN','AGND',1810,1280,s,90)
for node,x in [('HV_RAW',1610),('HV_IN',1810)]:
 rr('RDIS'+node+'A','100k_1w',node,node+'_BLEED',x,1450,s,90)
 rr('RDIS'+node+'B','100k_1w',node+'_BLEED','AGND',x,1550,s,90)
add('QHV','hv_nmos',{'1':'HV_GATE','2':'HV_IN','3':'HV_SOURCE'},2110,1230,s)
rr('RIL1','10_1w','HV_SOURCE','BPLUS',2240,1270,s)
rr('RIL2','10_1w','HV_SOURCE','BPLUS',2240,1360,s)
qn('QIL','BPLUS','HV_SOURCE','HV_GATE',2220,1510,s)
dd('DZGS','z_gate_12v','HV_SOURCE','HV_GATE',1980,1370,s)
# Bias feed series resistors keep each1206 within working voltage/power.
for i in range(4):
 rr('RGF'+str(i+1),'47k_025w','HV_IN' if i==0 else 'GF'+str(i),'HV_GATE' if i==3 else 'GF'+str(i+1),1930+i*110,1110,s)
qn('QERR','ZREF','HV_FB','HV_GATE',2130,1700,s)
rr('RFB1','221k_025w','BPLUS','HV_FB',2240,1620,s,90)
rr('RFB2','10k_025w','HV_FB','AGND',2240,1790,s,90)
for i in range(4):rr('RZF'+str(i+1),'22k_025w','HV_IN' if i==0 else 'ZF'+str(i),'ZREF' if i==3 else 'ZF'+str(i+1),1240+i*110,1810,s)
dd('DZREF','z_ref_6v2','AGND','ZREF',1810,1700,s,90)
cc('CZREF','control_470u25','ZREF','AGND',1920,1700,s,90)
cc('CGATE','signal_4u7film','HV_GATE','AGND',1980,1500,s,90)
cc('CBP','hv_220u400','BPLUS','AGND',2380,1510,s,90)
rr('RBP','100k_1w','BPLUS','AGND',2380,1730,s,90)
note(1240,1880,'B+ target~160V; current limit~0.65V/5R=130mA. Loop/SOA NOT qualified.')
note(1240,1910,'QHV IXTH30N50L2: G1 D2 S3; tab=D. Insulated heatsink required.')
s='06 DC HEATERS / ELEVATION'
two('F3','fuse_heater_5a','HTR_A','HTR_AF',2710,1220,s)
for ref,a,k,x,y in [('DF1','HTR_AF','HRAW',2880,1190),('DF2','HTR_B','HRAW',2880,1360),('DF3','HMINUS','HTR_AF',2880,1270),('DF4','HMINUS','HTR_B',2880,1440)]:dd(ref,'d_heater_sb560',a,k,x,y,s)
for i in range(4):cc('CHF'+str(i+1),'heater_3300u25','HRAW','HMINUS',3070+i*120,1300,s,90)
add('UH','heater_ldo',{'1':'HADJ','2':'HPLUS','3':'HRAW'},3640,1210,s)
rr('RH1','121_025w','HPLUS','HADJ',3790,1300,s,90)
rr('RH2','487_025w','HADJ','HMINUS',3790,1420,s,90)
cc('CHO','control_470u25','HPLUS','HMINUS',3950,1300,s,90)
cc('CHA','delay_100u25','HADJ','HMINUS',3660,1420,s)
dd('DHR','d_aux_1n4007','HPLUS','HRAW',3520,1100,s)
dd('DHA','d_aux_1n4007','HADJ','HPLUS',3780,1110,s)
rr('RHEU','200k_1w','BPLUS','HMINUS',3170,1630,s,90)
rr('RHED','100k_1w','HMINUS','AGND',3170,1760,s,90)
cc('CHE','hv_220u400','HMINUS','AGND',3380,1700,s,90)
note(2660,1840,'HPLUS-HMINUS ~6.3V; HMINUS elevation~53V. NEVER bond HMINUS to chassis.')
note(2660,1870,'LM1084 ADJ1 OUT2 IN3; tab=OUT. >=2.5A thermal design; insulated sink <=1.5C/W candidate.')
s='07 AUXILIARY DC'
for ref,a,k,x,y in [('DA1','AUX_A','AUX_RAW',180,2210),('DA2','AUX_B','AUX_RAW',180,2380),('DA3','AGND','AUX_A',180,2290),('DA4','AGND','AUX_B',180,2460)]:dd(ref,'d_aux_1n4007',a,k,x,y,s)
cc('CAUX','heater_3300u25','AUX_RAW','AGND',380,2340,s,90)
rr('RAUX','470_025w','AUX_RAW','AUX_Z',600,2180,s)
dd('DZAX','z_aux_13v','AGND','AUX_Z',650,2350,s,90)
cc('CAXZ','control_470u25','AUX_Z','AGND',810,2350,s,90)
qn('QAUX','AUX12','AUX_Z','AUX_RAW',970,2220,s,'aux_npn_bd139')
cc('CAXO','control_470u25','AUX12','AGND',1120,2350,s,90)
note(120,2570,'AUX12 ~12.3V; QAUX BD13910S E1 C2 B3 / tab C; small heatsink required')
s='08 DELAY / RELAY DRIVE / POWER LOSS'
rr('RT','100k_025w','AUX12','TIMER',1540,2180,s)
cc('CT','control_470u25','TIMER','AGND',1650,2350,s,90)
dd('DZT','z_timer_5v1','ZT_OUT','TIMER',1730,2180,s)
rr('RZBASE','47k_025w','ZT_OUT','D1B',1840,2180,s)
qn('QD1','D2B','D1B','COIL_LOW',1960,2190,s)
qn('QD2','D3B','D2B','COIL_LOW',2110,2310,s)
qn('QD3','AGND','D3B','COIL_LOW',2260,2430,s,'aux_npn_bd139')
rr('RDB','100k_025w','D1B','AGND',1830,2390,s,90)
rr('RDE','10k_025w','D3B','AGND',2110,2490,s,90)
# Flyback diode + zener gives faster release than a plain flyback diode.
dd('DFLY','d_aux_1n4007','COIL_LOW','FLY_K',2320,2190,s)
dd('DZFLY','z_flyback_24v','AUX12','FLY_K',2470,2190,s)
# Delay reset via diode when AUX collapses; independent AC-loss detector is not fitted.
dd('DRESET','d_small_1n4148','TIMER','AUX12',1520,2310,s)
rr('ROFF','1k_025w','AUX12','AGND',1450,2480,s,90)
note(1430,2620,'Turn-on delay ~40s (RC/beta/temp dependent); 24V flyback clamp, dropout must be measured')
s='09 BIPOLAR DC FAULT / TEST BOUNDARY'
for ch,x in [('L',2830),('R',3630)]:
 rr('RSEN1'+ch,'47k_025w',ch+'_OUT','SEN_M_'+ch,x,2150,s)
 rr('RSEN2'+ch,'47k_025w','SEN_M_'+ch,'SEN_AC_'+ch,x+130,2150,s)
 for i,a,k,xx,yy in [(1,'SEN_AC_'+ch,'OP_P_'+ch,x+200,2250),(2,'AGND','OP_P_'+ch,x+200,2400),(3,'OP_N_'+ch,'SEN_AC_'+ch,x+200,2320),(4,'OP_N_'+ch,'AGND',x+200,2470)]:
  dd('DS'+ch+str(i),'d_aux_1n4007',a,k,xx,yy,s)
 add('UO'+ch,'fault_opto',{'1':'OP_P_'+ch,'2':'OP_N_'+ch,'3':'AGND','4':'D1B'},x+480,2330,s)
note(2810,2600,'Full-wave sensing trips either polarity; LTV-817 phototransistor pulls QD1 base low.')
note(2810,2630,'94k input limits HV fault current; CTR-dependent trip threshold and relay cutoff UNQUALIFIED.')
note(2810,2660,'CO worst-case leakage can exceed 2mV at16/18R. NO REAL HEADPHONES pending faults/noise tests.')
note(2810,2690,'Relay67-1-A-12/1: contact1/4, coil2/3. 3A AND50W limits; arc interruption not qualified.')
# Allocate conventional physical references; preserve descriptive aliases separately.
counts={};refmap={}
for p in parts:
 old=p['ref'];key=p['key']
 prefix=('RV' if key=='pot_dual10k_log' else 'SW' if key in ['gain_dpdt','mains_switch'] else 'LK' if old=='LK1' else re.match('[A-Za-z]+',old).group()[0])
 counts[prefix]=counts.get(prefix,0)+1
 p['alias']=old;p['ref']=prefix+str(counts[prefix]);refmap[old]=p['ref']
(R/'reference-map.json').write_text(json.dumps(refmap,indent=2)+'\n')
for n in notes:
 for old in sorted(refmap,key=len,reverse=True):
  n['text']=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(old)+r'(?![A-Za-z0-9_])',refmap[old],n['text'])
# PE and audio star are electrically bonded by the explicit external LK1 strap.
# The separate protective conductor remains a physical construction requirement.
for p in parts:
 p["pins"]={k:("AGND" if v=="PE" else v) for k,v in p["pins"].items()}
# Authoritative fresh candidate connectivity.
used={p['key'] for p in parts};defs={}
for key in used:
 if key in P:
  z=P[key];pins=z['pins'];src={'provider':'easyeda-pro','library_uuid':z['library_uuid'],'device_uuid':z['device_uuid'],'symbol_uuid':z['symbol_uuid'],'footprint_uuid':z['footprint_uuid'],'manufacturer':z['manufacturer'],'manufacturer_part_number':z['mpn'],'supplier_id':z['lcsc'],'raw_pin_types':{p['number']:p['raw_type'] or 'Missing' for p in pins}}
  desc=z['intended_role'];review='unreviewed';auth='source_library';fp=z['footprint_uuid'];sym=z['symbol_uuid']
 else:
  if key=='transformer_contract':mapping={str(i):'PROPOSED_TERMINAL_'+str(i) for i in range(1,9)};desc='Custom transformer terminal contract, unverified physical pins';mpn='QPCB-TX6H30-100VA-DRAFT'
  else:mapping=EX[key]['physical_pin_functions'];desc=EX[key]['notes'];mpn=EX[key]['mpn']
  pins=[{'number':n,'name':f,'raw_type':'Passive'} for n,f in mapping.items()];src={'provider':'datasheet-custom-candidate','manufacturer_part_number':mpn,'raw_pin_types':{p['number']:p['raw_type'] for p in pins}};review='unreviewed';auth='source_library';fp='';sym=''
 defs['project:'+key]={'kind':'physical','category':'candidate','reference_prefix':'X','pins':[{'number':z['number'],'name':z.get('name') or z['number'],'type':({'1':'input','2':'power_out','3':'power_in'}[z['number']] if key=='heater_ldo' else 'passive')} for z in pins],'description':desc,'source':src,'review':{'status':review,'pin_type_authority':'project_library','note':'Analog passive terminal classification explicitly reviewed; LM1084 IN power_in, OUT power_out, ADJ input. Raw library types remain in source.raw_pin_types and native library. Physical/ratings approval is separate in parts.audit.json and exceptions.'}}
 if fp:defs['project:'+key]['footprint']=fp
 if sym:defs['project:'+key]['symbol']=sym
nets={}
for p in parts:
 for pin,net in p['pins'].items():
  if net is not None:nets.setdefault(net,[]).append(p['ref']+'.#'+pin)
spec={'spec':'board-spec/v0.1','project':{'name':'6H30Pi-Candidate-OneSheet','description':'Complete drawing candidate. Not electrically qualified; transformer terminals proposed, socket footprints unresolved; no real headphones.'},'libraries':[],'definitions':defs,'instances':{p['ref']:{'part':'project:'+p['key']} for p in parts},'connections':[{'net':n,'endpoints':ends} for n,ends in nets.items()],'constraints':[],'outputs':[]}
for p in parts:
 nc=['#'+k for k,v in p['pins'].items() if v is None]
 if nc:spec['instances'][p['ref']]['no_connects']=nc
(R/'topology-candidate.json').write_text(json.dumps({'parts':parts,'notes':notes,'nets':nets,'known_failures':['bipolar DC detector threshold and cutoff time not qualified','output capacitor worst-case leakage above target','transformer terminal contract not confirmed','custom part footprints unresolved']},indent=2,ensure_ascii=False)+'\n')
(R/'boardspec.yaml').write_text(json.dumps(spec,indent=2,ensure_ascii=False)+'\n')
with (R/'BOM-candidate.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Reference','MPN','LCSC','Purpose','Status'])
 for p in parts:
  z=P.get(p['key'],EX.get(p['key'],{}));w.writerow([p['ref'],z.get('mpn','QPCB-TX6H30-100VA-DRAFT'),z.get('lcsc',''),p['section'],'CANDIDATE; application not qualified'])
print(len(parts),'instances;',len(nets),'nets')
