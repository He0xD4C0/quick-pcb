#!/usr/bin/env python3
"""Discrete timer/DC detector fixtures generated from circuit.json.
Relay timing and tube warm-up are explicit scenario assumptions, not vendor models.
"""
import sys,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).parent));from simulate_audio import run,table,ROOT

def protection():
 data=json.loads((ROOT/'circuit.json').read_text());lines=[]
 for c in data['components']:
  if c['page'][:2] not in ['07','08','09']:continue
  ns=[('0' if v=='AGND' else v) for v in c['pins'].values()];ref=c['ref'];typ=c['type'];v=c['value']
  if typ in ['R','C']:lines.append(f'{ref} {" ".join(ns)} {v}')
  elif typ=='NPN':lines.append(f'{ref} {ns[2]} {ns[1]} {ns[0]} QHV')
  elif typ=='D':
   mod='DZ51' if v.startswith('5.1V') else 'DZ24' if v.startswith('24V') else 'DFAST'
   lines.append(f'{ref} {ns[0]} {ns[1]} {mod}')
 return '\n'.join(lines)+'''
RCOIL AUX12 COIL_LO 500
* Proxy relay: 9 V pickup/hold threshold; mechanical release latency NOT modeled here.
BCTRL RELAY 0 V=V(AUX12,COIL_LO)
SLC L_OUT HP_L RELAY 0 CONTACT
SRC R_OUT HP_R RELAY 0 CONTACT
.model CONTACT SW(RON=.15 ROFF=1e12 VT=9 VH=.1)
.model QHV NPN(Is=1e-14 BF=80 VAF=80 CJE=12p CJC=5p)
.model DFAST D(Is=2n N=1.7 RS=1 CJO=4p TT=4n)
.model DZ51 D(Is=1n N=1.5 RS=5 BV=5.1 IBV=.001)
.model DZ24 D(Is=1n N=1.5 RS=5 BV=24 IBV=.001)
'''

def fixture(case):
 start=case in ['startup','asymmetric_warmup','quick_restart']
 aux='PWL(0 0 .01 0 .03 12)' if start else '12'
 ac='PWL(0 0 .01 0 .03 15)' if start else '15'
 mid='PWL(0 0 5 0 15 82.13)' if start else '82.13'
 if case=='asymmetric_warmup':mid='PWL(0 0 25 0 70 82.13)'
 if case=='quick_restart':
  aux='PWL(0 0 .01 0 .03 12 100 12 100.01 0 102 0 102.01 12)'
  ac=aux;mid='PWL(0 0 5 0 15 82.13 100 82.13 101 70 102 70 110 82.13)'
 if case=='power_off':aux='PWL(0 12 .05 12 .25 0)';ac='PWL(0 15 .05 15 .0501 0)';mid='PWL(0 82.13 .05 82.13 .5 0)'
 extra='';load=16
 if case=='dc_fault_positive':extra='VFAULT FL 0 PWL(0 0 .05 0 .05001 1)\nSFAIL L_MID L_OUT FL 0 FAIL\n.model FAIL SW(RON=.01 ROFF=1e12 VT=.5 VH=.1)'
 if case=='dc_fault_negative':extra='VNEG L_OUT 0 PWL(0 0 .05 0 .05001 -5)'
 if case=='leakage':extra='ILEAK L_MID L_OUT 125u'
 if case=='open_capacitor':extra='';cap='1p'
 else:cap='1000u'
 if case=='short_output':load=.1
 if case=='no_load':load=1e12
 if case=='gain_switch':extra='VSIG SIGNAL 0 PWL(0 0 .05 0 .05001 .14 .05002 .014 .05003 0)\nRSIG SIGNAL L_OUT 25'
 net='Protection test fixture - generic models\n.options method=gear reltol=1e-5\n'+protection()+f'''
VAUX AUX12 0 {aux}
VAC AUX_A 0 {ac}
VML ML 0 {mid}
VMR MR 0 {'PWL(0 0 5 0 15 82.13)' if start else '82.13'}
* Linear Thevenin fault proxy. Real tube current limiting / internal capacitance NOT covered.
RML ML L_MID 25
RMR MR R_MID 25
RDC_L L_MID 0 100k
RDC_R R_MID 0 100k
CL L_MID L_OUT {cap}
CR R_MID R_OUT 1000u
RBL L_OUT 0 10k
RBR R_OUT 0 10k
RHP_L HP_L 0 100k
RHP_R HP_R 0 100k
RL HP_L 0 {load}
RR HP_R 0 {load}
{extra}
'''
 return net,180 if start else .5, .002 if start else .00001

def main():
 out={'assumptions':['Warm-up ramp is a stress scenario, not a validated thermal tube model.','Relay ideal contact threshold excludes mechanical latency; therefore optimistic.','Cap-short source is 82.13 V with 25 ohm Thevenin impedance, not nonlinear tube simulation.','Fault energy has no manufacturer-approved safe threshold for these IEMs. Any large unqualified excursion blocks use.'],'cases':{}}
 fig,axs=plt.subplots(2,2,figsize=(12,7))
 for case in ['startup','asymmetric_warmup','quick_restart','power_off','dc_fault_positive','dc_fault_negative','leakage','open_capacitor','short_output','no_load','gain_switch']:
  net,end,step=fixture(case);name='protect_'+case
  run(name,net,f'tran {step} {end} 0 {step}\nwrdata {name}.dat v(hp_l) v(hp_r) v(relay) v(timer) v(l_out) v(refhi) v(reflo)')
  a=table(name+'.dat');t=a[:,0];vl=a[:,1];coil=a[:,3];on=coil>9
  energy=float(np.trapezoid(vl**2/16,t))
  r={'max_abs_output_V':float(max(abs(vl))),'energy_into_16ohm_J':energy if case not in ['short_output','no_load'] else None,'relay_on_first_s':float(t[np.flatnonzero(on)[0]]) if any(on) else None,'relay_at_end_V':float(coil[-1]),'timer_end_V':float(a[-1,4]),'dc_end_V':float(vl[-1]),'refhi_end_V':float(a[-1,6]),'reflo_end_V':float(a[-1,7])}
  if case in ['dc_fault_positive','dc_fault_negative','power_off']:
   off=np.flatnonzero((t>=.05)&(~on));r['optimistic_release_after_event_s']=float(t[off[0]]-.05) if len(off) else None
  out['cases'][case]=r
  if case in ['startup','asymmetric_warmup','dc_fault_positive','power_off']:
   ax=axs.flat[['startup','asymmetric_warmup','dc_fault_positive','power_off'].index(case)];ax.plot(t,vl,label='HP left V');ax.plot(t,coil,label='Coil voltage');ax.set_title(case);ax.set_xlabel('Time (s)');ax.grid(alpha=.25);ax.legend()
 fig.tight_layout();fig.savefig(ROOT/'results/protection_response.png',dpi=170)
 (ROOT/'results/protection.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
