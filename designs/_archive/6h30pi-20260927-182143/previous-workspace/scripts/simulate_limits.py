#!/usr/bin/env python3
"""Deterministic sensitivity, noise and ripple tests beyond nominal audio fixture."""
import sys,json,re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).parent))
from simulate_audio import circuit,run,table,steady,distortion,ROOT

def main():
 out={'random_seed':630,'tolerance_samples':[],'mode_vs_volume':[],'model_alternative_50mV':{},'noise':{},'psrr':{}}
 for load in [16,18]:
  out['model_alternative_50mV'][str(load)]=distortion('alt50_'+str(load),.05,load=load,model='6h30pi_eb_plate_alternative.lib')
  net=circuit(load=load).replace('AC 1 SIN','AC 0 SIN').replace('VB BPLUS 0 160','VB BPLUS 0 DC 160 AC 1')
  name='psrr_'+str(load);run(name,net,f'ac dec 60 10 100000\nwrdata {name}.dat v(hp)')
  a=table(name+'.dat');g=np.hypot(a[:,1],a[:,2]);out['psrr'][str(load)]={str(f):float(np.interp(f,a[:,0],g)) for f in [50,100,200,1000]}
  log=run('noise_'+str(load),circuit(load=load),'noise v(hp) VIN dec 100 20 20000\nprint onoise_total inoise_total')
  vals={k:float(v) for k,v in re.findall(r'(?im)^(onoise_total|inoise_total)\s*=\s*([\deE+.\-]+)',log)}
  out['noise'][str(load)]=vals
 for volume in [.1,.5,1]:
  for src in [0.01,100,1000]:
   hi=steady(f'vol_hi_{volume}_{src}',volume=volume,source_r=src)[0]
   lo=steady(f'vol_lo_{volume}_{src}',volume=volume,source_r=src,low=True)[0]
   out['mode_vs_volume'].append({'volume_fraction':volume,'source_ohm':src,'difference_dB':float(20*np.log10(hi['gain_1k']/lo['gain_1k']))})
 rng=np.random.default_rng(630)
 for i in range(32):
  kw=dict(bplus=rng.uniform(154,164),rk=68*rng.uniform(.99,1.01),rs=127*rng.uniform(.99,1.01),cap=.001*rng.uniform(.8,1.2),scale1=rng.uniform(.8,1.2),scale2=rng.uniform(.8,1.2),mus1=rng.uniform(.9,1.1),mus2=rng.uniform(.9,1.1))
  op=steady('tol_'+str(i),**kw)[0];thd=distortion('tolTHD_'+str(i),.05,**kw)
  out['tolerance_samples'].append({'parameters':kw,'steady':op,'thd_50mV':thd})
 fig,ax=plt.subplots(1,2,figsize=(10,4));s=out['tolerance_samples'];ax[0].plot([x['steady']['gain_1k'] for x in s],[x['thd_50mV']['thd_percent'] for x in s],'o');ax[0].axhline(.1,color='red',ls='--');ax[0].set(xlabel='16 ohm high gain',ylabel='THD at 50 mVrms (%)',title='Tube mismatch + passive tolerance')
 ax[1].plot([max(x['steady']['p_upper_W'],x['steady']['p_lower_W']) for x in s],'o');ax[1].axhline(4,color='red',ls='--');ax[1].set(xlabel='Fixed-seed scenario index',ylabel='Worst half plate dissipation (W)',title='Samples are not a population distribution')
 for a in ax:a.grid(alpha=.25)
 fig.tight_layout();fig.savefig(ROOT/'results/tolerance_response.png',dpi=180)
 out['scope']=['Random cases are sensitivities, not a statistical tube production model.','Resistor thermal noise only; tube intrinsic, microphonic, heater and LDO/zener noise omitted.','THD uses generic curve-derived models; tiny computed values near 0.003% numerical floor are not precision claims.','Short/open and switching fixtures in protection script are simplified scenarios.']
 (ROOT/'results/limits.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps({k:v for k,v in out.items() if k!='tolerance_samples'},indent=2));print('maxTHD',max(x['thd_50mV']['thd_percent'] for x in s))
if __name__=='__main__':main()
