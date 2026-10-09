#!/usr/bin/env python3
from pathlib import Path
import sys,json,numpy as np
sys.path.insert(0,str(Path(__file__).parent));from simulate_audio import circuit,run,table,ROOT
out={}
for load in [.1,16,18,1e9]:
 name='drive1V_'+str(load);net=circuit(load=load,amp=2**.5).replace('XUP PA GU MID','VUP PA PA_INT 0\nXUP PA_INT GU MID').replace('XLO MID GL K','VLO MID MID_INT 0\nXLO MID_INT GL K')
 run(name,net,f'tran 2.5u .03 .02 2.5u\nwrdata {name}.dat v(hp) i(vup) i(vlo) v(gu,mid) v(gl,k)')
 a=table(name+'.dat');t=a[:,0];avg=lambda v:float(np.trapezoid(v,t)/(t[-1]-t[0]))
 out[str(load)]={'input_Vrms':1,'output_Vrms':avg(a[:,1]**2)**.5,'output_peak_V':float(max(abs(a[:,1]))),'upper_Imax_A':float(max(a[:,2])),'lower_Imax_A':float(max(a[:,3])),'upper_grid_max_V':float(max(a[:,4])),'lower_grid_max_V':float(max(a[:,5]))}
(ROOT/'results/overload.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
