#!/usr/bin/env python3
"""Actual curve-derived tube circuit with hypothetical emission ramps.
This exercises cold/hot/nonmatching conduction; it is NOT a warmup prediction.
"""
import json,sys,re
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).parent));from simulate_audio import circuit,run,table,ROOT

def main():
 out={'scope':'No measured heater model. Ramps vary emission in the fitted current equation; protective relay forced OPEN in these raw node tests.','cases':{}}
 lib=(ROOT/'models/6h30pi_eb.lib').read_text()
 for name,up,lo in [('both_cold','min(1,max(0,(time-5)/10))','min(1,max(0,(time-5)/10))'),('lower_late','min(1,max(0,(time-5)/10))','min(1,max(0,(time-25)/45))'),('upper_late','min(1,max(0,(time-25)/45))','min(1,max(0,(time-5)/10))')]:
  net=circuit(load=16,amp=0)
  net=re.sub(r'^\.include .*$', '.global WARMUP WARMLO\n'+lib.replace('.subckt H30 ','.subckt H30UP ').replace('.ends H30','.ends H30UP').replace('SCALE*W*','SCALE*V(WARMUP)*')+'\n'+lib.replace('.subckt H30 ','.subckt H30LO ').replace('.ends H30','.ends H30LO').replace('SCALE*W*','SCALE*V(WARMLO)*'),net,flags=re.M)
  net=net.replace('XUP PA GU MID H30','XUP PA GU MID H30UP').replace('XLO MID GL K H30','XLO MID GL K H30LO')
  net=net.replace('VB BPLUS 0 160','VB BPLUS 0 PWL(0 0 .1 0 3 160)')
  net=net.replace('RCONTACT OUT HP 0.15','RCONTACT OUT HP 1e12')
  net+='\nBWU WARMUP 0 V='+up+'\nBWL WARMLO 0 V='+lo+'\nREL1 BPLUS HELEV 150k\nREL2 HELEV 0 47k\nCEL HELEV 0 47u\n'
  run('warm_'+name,net,f'tran 2m 100 0 2m\nwrdata warm_{name}.dat v(mid) v(out) v(helev) v(k) v(pa) v(gu)')
  a=table('warm_'+name+'.dat');vpk=a[:,5]-a[:,1];vk=a[:,1]-a[:,3]
  out['cases'][name]={'raw_out_peak_V':float(max(abs(a[:,2]))),'upper_cathode_to_heater_abs_max_V':float(max(abs(vk))),'lower_cathode_to_heater_abs_max_V':float(max(abs(a[:,4]-a[:,3]))),'minimum_output_cap_voltage_V':float(min(a[:,1]-a[:,2])),'upper_plate_to_cathode_min_V':float(min(vpk)),'raw_out_at_60s_V':float(np.interp(60,a[:,0],a[:,2]))}
 (ROOT/'results/startup.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
