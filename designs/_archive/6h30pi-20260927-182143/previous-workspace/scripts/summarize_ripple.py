#!/usr/bin/env python3
from pathlib import Path
import sys,json,numpy as np
sys.path.insert(0,str(Path(__file__).parent));from simulate_audio import ROOT,table
out={'method':'Linear post-processing of steady generic supply waveform through audio B+ transfer function; no heater/magnetic coupling or intrinsic device noise.','cases':{}}
for line in [.9,1,1.1]:
 a=table(f'hv_{line}.dat');t=np.linspace(a[-1,0]-.1,a[-1,0],16384,endpoint=False);v=np.interp(t,a[:,0],a[:,3]);v-=v.mean();f=np.fft.rfftfreq(len(t),t[1]-t[0]);vrms=np.abs(np.fft.rfft(v))*np.sqrt(2)/len(t)
 for load in [16,18]:
  b=table(f'psrr_{load}.dat');g=np.interp(f,b[:,0],np.hypot(b[:,1],b[:,2]));band=(f>=20)&(f<=20000);o=vrms*g
  out['cases'][f'{220*line:g}V_{load}ohm']={'Bplus_100Hz_Vrms':float(np.interp(100,f,vrms)),'HP_100Hz_Vrms':float(np.interp(100,f,o)),'HP_20Hz_20kHz_ripple_Vrms':float(np.sqrt(np.sum(o[band]**2)))}
(ROOT/'results/ripple.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
