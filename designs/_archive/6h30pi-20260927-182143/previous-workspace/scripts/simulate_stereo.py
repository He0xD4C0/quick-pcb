#!/usr/bin/env python3
"""Full stereo connection manifest -> integrated generic-model feasibility fixture.
Physical terminals remain in BoardSpec. Ideal transformer and LDO approximations.
"""
import sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).parent));from simulate_audio import ROOT,run,table

def make():
 data=json.loads((ROOT/'circuit.json').read_text());out=['Full stereo WCF and three winding power supply - feasibility only',f'.include {ROOT/"models/6h30pi_eb.lib"}', '.options method=gear reltol=3e-5 abstol=1e-10']
 refs={}
 for c in data['components']:
  typ=c['type'];r=c['ref'];v=c['value'];n={k:('0' if v=='AGND' else v) for k,v in c['pins'].items()};ns=list(n.values());refs[c['alias']]=r
  if typ in ['R','C']:out.append(f'{r} {" ".join(ns)} {v}')
  elif typ=='D':
   mod='DREC' if '4007' in v else 'DSCH' if 'MBR' in v else 'DFAST'
   if 'zener' in v:
    bv=v.split('V')[0];mod='DZ_'+bv.replace('.','_');out.append(f'.model {mod} D(IS=1n RS=5 BV={bv} IBV=.001)')
   out.append(f'{r} {n["A"]} {n["K"]} {mod}')
  elif typ=='NPN':out.append(f'{r} {n["3"]} {n["2"]} {n["1"]} QHV')
  elif typ=='MOS':out.append(f'M{r} {n["2"]} {n["1"]} {n["3"]} {n["3"]} MPASS')
  elif typ=='TUBE':
   out.extend([f'X{r}UP {n["6"]} {n["7"]} {n["8"]} H30',f'X{r}LO {n["1"]} {n["2"]} {n["3"]} H30',f'R{r}H {n["4"]} {n["5"]} 7'])
  elif typ=='LINK':out.append(f'R{r}LINK {ns[0]} {ns[1]} .05')
  elif typ=='SW':out.extend([f'R{r}L {n["L1"]} {n["L2"]} .01',f'R{r}N {n["N1"]} {n["N2"]} .01'])
  elif typ=='GAIN':
   for ch in ['L','R']:out.append(f'R{r}{ch} {n[ch+"C"]} {n[ch+"H"]} .01')
  elif typ=='POT':
   for ch in ['L','R']:out.extend([f'R{r}{ch}T {n[ch+"T"]} {n[ch+"W"]} .001',f'R{r}{ch}B {n[ch+"W"]} {n[ch+"B"]} 10k'])
  elif typ=='RELAY':out.extend([f'R{r}COIL {n["CA"]} {n["CB"]} 1000',f'S{r} {n["A"]} {n["B"]} {n["CA"]} {n["CB"]} CONTACT'])
 # Ideal winding voltage sources; includes explicit assumed copper resistance.
 out.extend(['VMAINS MAINS_L MAINS_N SIN(0 311.12698 50)','RNEUTRAL MAINS_N 0 1G','RPE PE 0 .001'])
 for name,ratio,rw in [('HV',150/220,35),('HTR',9.5/220,.18),('AUX',12/220,2)]:
  out.extend([f'B{name} {name}_X {name}_B V={ratio}*V(PRI_L,PRI_N)',f'RW{name} {name}_X {name}_A {rw}',f'REF{name} {name}_B 0 10Meg',f'CREF{name} {name}_B 0 1n'])
 out.extend(['BHEAT HIDEAL HMINUS V=max(0,min(6.3,V(HRAW,HMINUS)-1.5))','VHEAT HIDEAL HPLUS 0','BHEATIN HRAW HMINUS I=max(0,I(VHEAT))', 'VINL LSRC 0 0','VINR RSRC 0 0','RINL LSRC IN_L 100','RINR RSRC IN_R 100','RLOADL HP_L 0 16','RLOADR HP_R 0 18','.model DREC D(IS=10n RS=.25 N=1.5 CJO=20p TT=75n BV=1000)', '.model DSCH D(IS=20u N=1.15 RS=.025 CJO=500p BV=45)', '.model DFAST D(IS=2n N=1.7 RS=1 CJO=4p TT=4n)', '.model QHV NPN(IS=1e-14 BF=80 VAF=80 CJE=12p CJC=5p)', '.model MPASS NMOS(LEVEL=1 VTO=3.5 KP=.45 LAMBDA=.003 RD=1 RS=.2 CGSO=150p CGDO=30p)', '.model CONTACT SW(RON=.15 ROFF=1e12 VT=9 VH=.1)'])
 return '\n'.join(out)+'\n'

def main():
 import subprocess
 net=make();(ROOT/'simulation/stereo-generic.cir').write_text(net.replace(str(ROOT/'models'), '../models')+'\n.control\ntran 100u 10 0 100u\nwrite stereo-generic.raw\nquit\n.endc\n.end\n')
 out={'scope':'Full manifest generic electrical model; cold 10s and initialized warm 2s. No qualified thermal/transformer/LDO model.','long_cold_attempt':{'status':'TIMEOUT','duration_requested_s':60,'wall_timeout_s':90,'attempted_max_steps_s':[0.0001,0.001]},'cases':{}}
 initial='\n.ic v(HV_RAW)=200 v(HV_IN)=198 v(BPLUS)=160 v(HV_GATE)=164 v(HV_SOURCE)=160.4 v(HV_ZREF)=6.2 v(HV_FB)=6.9 v(HMINUS)=38.1 v(HPLUS)=44.4 v(HRAW)=50 v(HADJ)=43.15 v(AUX_RAW)=15 v(AUX12)=12.3 v(AUX_Z)=13 v(TIMER)=6.3 v(L_BIAS)=80 v(R_BIAS)=80 v(L_MID)=82 v(R_MID)=82 v(L_K)=2.5 v(R_K)=2.5 v(L_OUT)=0 v(R_OUT)=0 v(L_PA)=155 v(R_PA)=155\n'
 for label,end,tstart,suffix,fixture in [('cold',10,9.8,'',net),('warm',2,1.8,'uic',net+initial)]:
  name='stereo_'+label
  try:
   run(name,fixture,f'tran 100u {end} {tstart} 100u {suffix}\nwrdata {name}.dat v(bplus) v(hplus,hminus) v(l_mid) v(r_mid) v(hp_l) v(hp_r) v(aux12) v(hv_raw) v(hraw,hminus)')
   a=table(name+'.dat');t=a[:,0];avg=lambda v:float(np.trapezoid(v,t)/(t[-1]-t[0]))
   labels=['Bplus','Heater','L_mid','R_mid','L_hp','R_hp','Aux12','HVraw','HeaterRaw']
   out['cases'][label]={'status':'RAN','nodes':{key:{'mean_V':avg(a[:,i+1]),'ripple_Vpp':float(np.ptp(a[:,i+1]))} for i,key in enumerate(labels)}}
  except (subprocess.TimeoutExpired,RuntimeError) as exc:out['cases'][label]={'status':'UNVERIFIED','error':str(exc)}
 (ROOT/'results/stereo_integrated.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
