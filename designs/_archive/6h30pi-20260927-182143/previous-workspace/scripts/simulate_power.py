#!/usr/bin/env python3
"""Power feasibility fixtures; generic semiconductor models, NOT vendor signoff."""
from pathlib import Path
import sys,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).parent));from simulate_audio import run,table,ROOT

def hv(line=1,load=.079):
 return f'''HV supply: isolated 150 Vac winding and discrete regulator
.options method=gear reltol=1e-5
VSEC ACX AC2 SIN(0 {150*2**.5*line} 50)
RW ACX AC1 35
RREF AC2 0 10Meg
CREF AC2 0 1n
D1 AC1 RAW DREC
D2 AC2 RAW DREC
D3 0 AC1 DREC
D4 0 AC2 DREC
C1 RAW 0 220u
RF RAW HVIN 22
C2 HVIN 0 220u
RB1 RAW 0 100k
M1 HVIN GATE VS VS MPASS
RG HVIN GATE 47k
DZG VS GATE DZ12
RS VS BPLUS 4.7
QLIM GATE VS BPLUS QHV
QERR GATE FB ZREF QHV
RFU BPLUS FB 221k
RFL FB 0 10k
RZ HVIN ZREF 82k
DZ 0 ZREF DZ62
CZ ZREF 0 47u
CC GATE FB 10n
CO BPLUS 0 100u
RB2 BPLUS 0 100k
RL BPLUS 0 {160/load}
.model DREC D(Is=10n Rs=.25 N=1.5 CJO=20p TT=75n BV=1000 IBV=5u)
.model DZ62 D(Is=1n Rs=10 BV=6.2 IBV=.002)
.model DZ12 D(Is=1n Rs=5 BV=12 IBV=.001)
.model QHV NPN(Is=1e-14 BF=80 VAF=80 CJE=12p CJC=5p)
.model MPASS NMOS(Level=1 VTO=3.5 KP=.45 LAMBDA=.003 RD=1 RS=.2 CGSO=150p CGDO=30p)
'''

def heater(line=1,amps=1.8):
 return f'''Floating heater supply differential fixture, elevation tested separately
.options method=gear reltol=1e-5
VS AX A2 SIN(0 {9.5*2**.5*line} 50)
RW AX A1 .18
RREF A2 0 10Meg
CREF A2 0 1n
D1 A1 RAW DS
D2 A2 RAW DS
D3 0 A1 DS
D4 0 A2 DS
CI RAW 0 15000u
* Regulator abstraction: nominal 6.30 V, worst-case 1.5 V dropout.
BREG H 0 V=max(0,min(6.30,V(RAW)-1.5))
BLOAD RAW 0 I=({amps+.0104})*min(1,max(0,V(RAW)/7.8))
CO H CE 220u
RE CE 0 .2
.model DS D(Is=20u N=1.15 Rs=.025 CJO=500p BV=40)
'''

def main():
 out={'model_scope':'Generic rectifiers, BJT and MOSFET; heater LDO behavioral. No validated loop/SOA/thermal or transformer inrush model.','hv':{},'heater':{}}
 fig,axs=plt.subplots(1,2,figsize=(11,4))
 for line in [.9,1,1.1]:
  name=f'hv_{line}';run(name,hv(line),'tran 50u 3 2.8 50u\nwrdata '+name+'.dat v(raw) v(hvin) v(bplus) v(gate) v(vs) i(vsec)')
  a=table(name+'.dat');t=a[:,0];raw=a[:,1];v=a[:,3];i=a[:,-1]
  avg=lambda v: float(np.trapezoid(v,t)/(t[-1]-t[0]))
  out['hv'][str(line)]={'raw_Vmean':avg(raw),'raw_ripple_Vpp':float(np.ptp(raw)), 'Bplus_Vmean':avg(v),'Bplus_ripple_Vpp':float(np.ptp(v)), 'secondary_Arms':float(np.sqrt(avg(i*i))),'pass_W_est':avg((a[:,2]-v)*.079),'bulk_ripple_Arms_est':float(np.sqrt(avg((np.abs(i)-.079)**2)))}
  axs[0].plot(t-t[0],v,label=f'{line*220:g} VAC')
  name=f'heater_{line}';run(name,heater(line),'tran 50u 1 .8 50u\nwrdata '+name+'.dat v(raw) v(h) i(vs)')
  h=table(name+'.dat');t=h[:,0];out['heater'][str(line)]={'raw_min_V':float(h[:,1].min()),'raw_max_V':float(h[:,1].max()),'output_min_V':float(h[:,2].min()),'output_max_V':float(h[:,2].max()),'regulator_W':avg((h[:,1]-h[:,2])*1.8),'secondary_Arms':float(np.sqrt(avg(h[:,3]**2))),'bulk_ripple_Arms_est':float(np.sqrt(avg((np.abs(h[:,3])-1.8)**2)))}
  axs[1].plot(h[:,0]-h[0,0],h[:,1],label=f'{line*220:g} VAC raw')
 for ax in axs:ax.set(xlabel='Time (s)',ylabel='V');ax.grid(alpha=.3);ax.legend()
 axs[0].set_title('Discrete HV regulator / generic models');axs[1].set_title('Heater rectifier valley / LDO needs 7.8 V')
 fig.tight_layout();fig.savefig(ROOT/'results/power_response.png',dpi=180)
 (ROOT/'results/power.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
