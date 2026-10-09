#!/usr/bin/env python3
"""Audio-only ngspice regression from fresh physical-pin topology.
Ideal B+ / closed relays / nominal passives. NOT a complete PSU or protection validation.
"""
import json,subprocess,math
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1];O=R/'simulation';O.mkdir(exist_ok=True)
B=json.loads((R/'topology-candidate.json').read_text());L=json.loads((R/'parts.lock.json').read_text())['parts'];A=json.loads((R/'parts.audit.json').read_text())['reviews']
node=lambda s:'0' if s=='AGND' else s
parts=[p for p in B['parts'] if p['section'].startswith('02 L') or p['alias'] in ['RAL','RBL']]
def value(p):
 key=p['key']
 if key.startswith('r_'):return str(A[key]['ratings']['resistance_ohm'])
 return L[key]['library_properties']['Value'].replace('μ','u').replace('µ','u').replace('F','').replace('Ω','')
def deck(load,mode,peak=0.1,test=False):
 lines=['6H30Pi candidate fresh topology / AUDIO ONLY',f'.include "{R}/models/6h30pi_eb.lib"','Vb BPLUS 0 160',f'Vin IN_L 0 AC {0 if test else 1} SIN(0 {peak} 1000)',f'Rmode {"IN_L" if mode=="high" else "LOW_L"} SEL_L 1m','Rpotcontact SEL_L WIP_L 1m','Rpottrack WIP_L 0 10k',f'Rload HP_L 0 {load}']
 if test:lines.append('Itest 0 HP_L AC 1')
 for p in parts:
  ref=p['ref'];key=p['key'];pins=p['pins']
  if key.startswith(('r_','c_')):lines.append(f'{ref} {node(pins["1"])} {node(pins["2"])} {value(p)}')
  elif key=='tube_6h30pi_eb':
   for unit,plate,grid,cath in [('A','6','7','8'),('B','1','2','3')]:lines.append(f'X{ref}{unit} {pins[plate]} {pins[grid]} {pins[cath]} H30')
  elif key=='relay_hv':lines.append(f'Rcontact {pins["1"]} {pins["4"]} .12')
 return '\n'.join(lines)+'\n'
def run(name,text):
 folder=O/name;folder.mkdir(exist_ok=True);p=folder/'circuit.cir';p.write_text(text)
 q=subprocess.run(['ngspice','-b',str(p)],cwd=folder,text=True,capture_output=True,timeout=60)
 (folder/'ngspice.log').write_text(q.stdout+q.stderr)
 if 'Error:' in q.stderr or 'run simulation(s) aborted' in q.stderr:raise RuntimeError(name+q.stderr[-1000:])
 return folder
report={'scope':'AUDIO ONLY; ideal160V source, ideal capacitors, closed relay0.12ohm. No PSU/heater/noise/startup/fault validation. Model cross-family error46.70%; not hardware qualification.','loads':{}}
for load in [16,18]:
 modes={}
 for mode in ['high','low']:
  text=deck(load,mode)+'.control\nset wr_singlescale\nop\nwrdata op.dat v(L_PA) v(L_MID) v(L_K) v(L_GU)\nac dec 100 10 100000\nwrdata ac.dat v(HP_L)\nquit\n.endc\n.end\n'
  folder=run(f'{load}ohm-{mode}',text);ac=np.loadtxt(folder/'ac.dat');f=ac[:,0];v=ac[:,1]+1j*ac[:,2]
  gain=float(np.interp(1000,f,abs(v)));db=20*np.log10(abs(v)/gain)
  op=np.loadtxt(folder/'op.dat').flatten();pa,mid,k,gu=op[1:5];iq=k/68
  modes[mode]={'gain_1k':gain,'gain_1k_dB':20*math.log10(gain),'response_dB_at_20_20k':[float(np.interp(z,f,db)) for z in [20,20000]],'op':{'plate_upper_V':pa,'mid_V':mid,'cathode_lower_V':k,'grid_upper_V':gu,'Iq_mA':iq*1e3,'Pa_upper_W':(pa-mid)*iq,'Pa_lower_W':(mid-k)*iq},'DC_output_ideal_cap_V':0}
 hi=modes['high']['gain_1k'];thd=[]
 for mv in [50,100]:
  peak=mv/1000*math.sqrt(2)/hi
  folder=run(f'{load}ohm-thd-{mv}mV',deck(load,'high',peak)+'.control\nset wr_singlescale\ntran 1u 50m 30m\nwrdata tran.dat v(HP_L)\nquit\n.endc\n.end\n')
  d=np.loadtxt(folder/'tran.dat');t=np.linspace(.030,.050,20000,endpoint=False);y=np.interp(t,d[:,0],d[:,1]);z=np.fft.rfft(y-y.mean())*2/len(t);bins=[20*i for i in range(1,11)];amps=abs(z[bins]);th=math.sqrt(sum(amps[1:]**2))/amps[0]*100
  thd.append({'target_mVrms':mv,'input_Vrms':peak/math.sqrt(2),'actual_output_mVrms':amps[0]/math.sqrt(2)*1000,'THD_10_harmonics_pct':th,'model_target_pass':bool(th<=(.1 if mv==50 else .5))})
 folder=run(f'{load}ohm-zout',deck(1e9,'high',test=True)+'.control\nset wr_singlescale\nac dec 100 10 100000\nwrdata zout.dat v(HP_L)\nquit\n.endc\n.end\n');d=np.loadtxt(folder/'zout.dat');z=abs(d[:,1]+1j*d[:,2])
 report['loads'][str(load)]={'modes':modes,'mode_difference_dB':20*math.log10(hi/modes['low']['gain_1k']),'THD':thd,'unloaded_output_impedance_ohm_20_1k_20k':[float(np.interp(f,d[:,0],z)) for f in [20,1000,20000]],'output_cap_datasheet_max_leakage_DC_mV':1.5*load,'acceptance':'NOT_PASSED: cap leakage bound, model uncertainty, omitted PSU/fault tests'}
(O/'audio-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
