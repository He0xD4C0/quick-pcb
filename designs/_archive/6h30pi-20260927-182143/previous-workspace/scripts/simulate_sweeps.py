#!/usr/bin/env python3
"""Record Rs choice, heater capacity corners and pad passive tolerances."""
import sys,json,itertools
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).parent));from simulate_audio import ROOT,run,table,circuit,distortion
from simulate_power import heater
balance={}
for rs in [115,120,124,127,130]:
 balance[str(rs)]={m:distortion('balance_'+str(rs)+'_'+m.split('.')[0],.05,rs=rs,model=m)['thd_percent'] for m in ['6h30pi_eb.lib','6h30pi_eb_plate_alternative.lib']}
(ROOT/'results/rs_model_balance.json').write_text(json.dumps(balance,indent=2)+'\n')
capacity={}
for line,capscale in itertools.product([.9,1,1.1],[.8,1,1.2]):
 n=f'heater_capacity_{line}_{capscale}';net=heater(line,2.5).replace('CI RAW 0 15000u',f'CI RAW 0 {15000*capscale}u')
 run(n,net,f'tran 50u 1 .8 50u\nwrdata {n}.dat v(raw) v(h) i(vs)');a=table(n+'.dat');t=a[:,0];avg=lambda v:float(np.trapezoid(v,t)/(t[-1]-t[0]))
 capacity[n]={'line_ratio':line,'cap_scale':capscale,'raw_min_V':float(a[:,1].min()),'output_min_V':float(a[:,2].min()),'secondary_Arms':avg(a[:,3]**2)**.5,'regulator_W':avg((a[:,1]-a[:,2])*2.5),'bulk_ripple_Arms':avg((np.abs(a[:,3])-2.5)**2)**.5}
(ROOT/'results/heater_capacity.json').write_text(json.dumps(capacity,indent=2)+'\n')
pad=[]
for k,(ra,rb,pot) in enumerate(itertools.product([.99,1.01],[.99,1.01],[.8,1.2])):
 gs=[]
 for low in [False,True]:
  n=f'padcorner_{k}_{low}';net=circuit(low=low).replace('RATT IN ATT 8.2k',f'RATT IN ATT {8200*ra}').replace('RSH ATT 0 1k',f'RSH ATT 0 {1000*rb}').replace('RVB WIPER 0 10000.0',f'RVB WIPER 0 {10000*pot}')
  run(n,net,f'ac lin 1 1000 1000\nwrdata {n}.dat v(hp)');a=np.atleast_2d(table(n+'.dat'));gs.append(float(np.hypot(a[0,1],a[0,2])))
 pad.append({'Ratt_scale':ra,'Rsh_scale':rb,'pot_scale':pot,'difference_dB':float(20*np.log10(gs[0]/gs[1]))})
(ROOT/'results/pad_tolerance.json').write_text(json.dumps(pad,indent=2)+'\n')
print('Heater worst',min(x['output_min_V'] for x in capacity.values()),'pad dB range',min(x['difference_dB'] for x in pad),max(x['difference_dB'] for x in pad))
