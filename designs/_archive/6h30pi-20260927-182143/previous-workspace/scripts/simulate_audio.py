#!/usr/bin/env python3
"""Reproducible ngspice audio tests. Behavioral tube model has NO noise source."""
from pathlib import Path
import json, subprocess, re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'results/raw'; RUN.mkdir(parents=True,exist_ok=True)

def circuit(load=16,low=False,model='6h30pi_eb.lib',bplus=160,rk=68,rs=127,
            cap=1e-3,scale1=1,scale2=1,mus1=1,mus2=1,source_r=100,volume=1,
            amp=.2,freq=1000,leak=0,emission1='1',emission2='1'):
    # Relay closed in steady audio tests. Protection is tested separately.
    atten='RATT IN ATT 8.2k\nRSH ATT 0 1k\n'+('RSW ATT SEL 0.01' if low else 'RTHRU IN SEL 0.01')
    return f'''Two 6H30Pi WCF stereo project - one channel test fixture
.include {ROOT/'models'/model}
.options reltol=1e-6 abstol=1e-11 vntol=1e-8 method=gear
VB BPLUS 0 {bplus}
VIN SRC 0 DC 0 AC 1 SIN(0 {amp} {freq})
RSOURCE SRC IN {source_r}
{atten}
RVT SEL WIPER {max(.001,1e4*(1-volume))}
RVB WIPER 0 {max(.001,1e4*volume)}
CIN WIPER GI 4.7u
RBIAS1 BPLUS BIAS 100k
RBIAS2 BIAS 0 100k
CBIAS BIAS 0 47u
RGRID BIAS GI 47k
RGSTOP GI GU 100
RSENSE BPLUS PA {rs}
XUP PA GU MID H30 SCALE={scale1} MUS={mus1} W={emission1}
XLO MID GL K H30 SCALE={scale2} MUS={mus2} W={emission2}
RGL GL GB 100
CFEED PA GB 4.7u
RLEAK GB 0 100k
RK K 0 {rk}
CK K 0 2200u
COUT MID CAPOUT {cap}
RESR CAPOUT OUT 0.15
ILEAK MID OUT DC {leak}
RMID MID 0 100k
RBLEED OUT 0 10k
RCONTACT OUT HP 0.15
RHP HP 0 100k
RMON OUT 0 100k
RL HP 0 {load}
'''

def run(name,net,control):
    path=RUN/f'{name}.cir'
    path.write_text(net+'\n.control\nset noaskquit\nset wr_singlescale\nset wr_vecnames\n'+control+'\nquit\n.endc\n.end\n')
    try:
        p=subprocess.run(['ngspice','-b',str(path)],cwd=RUN,text=True,capture_output=True,timeout=90)
    except subprocess.TimeoutExpired as exc:
        def decode(v):return v.decode(errors='replace') if isinstance(v,bytes) else (v or '')
        (RUN/f'{name}.log').write_text(decode(exc.stdout)+decode(exc.stderr)+'\nHARNESS_TIMEOUT_AFTER_90_SECONDS\n')
        raise
    log=p.stdout+p.stderr;(RUN/f'{name}.log').write_text(log)
    if p.returncode or re.search(r'(?im)^error',log):raise RuntimeError(f'{name}: '+log[-1600:])
    return log

def table(name):return np.loadtxt(RUN/name,skiprows=1)

def steady(name,**kw):
    log=run(name,circuit(**kw),f'op\nprint v(pa) v(gu) v(mid) v(gl) v(k) i(vb)\nac dec 60 10 100000\nwrdata {name}_ac.dat v(hp)\n')
    op={k:float(v) for k,v in re.findall(r'(?im)^(v\([a-z]+\)|i\(vb\))\s*=\s*([\deE+.\-]+)',log)}
    a=table(name+'_ac.dat');f=a[:,0];gain=np.hypot(a[:,1],a[:,2]);g1=float(np.interp(1000,f,gain))
    db=20*np.log10(gain/g1);band=(f>=20)&(f<=20000)
    iq=op['v(k)']/kw.get('rk',68)
    return {'gain_1k':g1,'response_20Hz_dB':float(np.interp(20,f,db)),
        'response_20kHz_dB':float(np.interp(20000,f,db)),
        'max_band_deviation_dB':float(max(max(abs(db[band])),abs(np.interp(20,f,db)),abs(np.interp(20000,f,db)))),'iq_A':iq,
        'p_upper_W':(op['v(pa)']-op['v(mid)'])*(iq+op['v(mid)']/100000),
        'p_lower_W':(op['v(mid)']-op['v(k)'])*iq,'op':op},a

def distortion(name,target,**kw):
    gain,_=steady(name+'_gain',**kw)
    amp=target*np.sqrt(2)/gain['gain_1k']
    freq=kw.pop('freq',1000)
    # Start from operating point, run 30 cycles; fourier from final full cycle.
    log=run(name,circuit(amp=amp,freq=freq,**kw),f'tran {1/freq/400} {30/freq} {20/freq} {1/freq/400}\nfourier {freq} v(hp)\nwrdata {name}_tran.dat v(hp) v(mid)\n')
    m=re.search(r'THD:\s*([\deE+.\-]+)',log)
    if not m:raise RuntimeError('Missing Fourier result '+name)
    return {'target_Vrms':target,'input_Vrms':amp/np.sqrt(2),'thd_percent':float(m[1])}

def main():
    results={'ngspice_version':subprocess.check_output(['ngspice','--version'],text=True).splitlines()[1],
             'nominal':{},'distortion':{},'corners':{},'model_alternative':{}}
    fig,ax=plt.subplots(1,2,figsize=(11,4))
    for load in [16,18,32,300,1e9]:
        for low in [False,True]:
            name=f'R{int(load)}_'+('low' if low else 'high');r,a=steady(name,load=load,low=low)
            results['nominal'][name]=r
            if load in [16,18,300] and not low:
                g=np.hypot(a[:,1],a[:,2]);ax[0].semilogx(a[:,0],20*np.log10(g/r['gain_1k']),label=f'{load} ohm')
        if load in [16,18]:
            for mv in [6.7,12.6,50,100,200]:results['distortion'][f'R{load}_{mv}mV']=distortion(f'thd_{load}_{mv}',mv/1000,load=load)
    # Measure driving point Z directly by current injection, input shorted.
    net=circuit(load=1e12).replace('AC 1 SIN','AC 0 SIN')+'\nITEST HP 0 AC 1\n'
    run('zout',net,'ac dec 60 10 100000\nwrdata zout.dat v(hp)')
    z=table('zout.dat');zm=np.hypot(z[:,1],z[:,2]);ax[1].loglog(z[:,0],zm)
    results['zout_ohm']={str(f):float(np.interp(f,z[:,0],zm)) for f in [20,100,1000,10000,20000]}
    for b in [144,160,176]:
        for s1,s2 in [(.8,1.2),(1.2,.8),(.8,.8),(1.2,1.2)]:
            name=f'corner_{b}_{s1}_{s2}';r,_=steady(name,bplus=b,scale1=s1,scale2=s2);results['corners'][name]=r
    for load in [16,18]:
        results['model_alternative'][str(load)]=distortion(f'alt_{load}',.1,load=load,model='6h30pi_eb_plate_alternative.lib')
        results['model_alternative'][str(load)]['steady']=steady(f'altop_{load}',load=load,model='6h30pi_eb_plate_alternative.lib')[0]
    for load in [16,18]:
        hi=results['nominal'][f'R{load}_high'];lo=results['nominal'][f'R{load}_low']
        hi['gain_difference_dB']=float(20*np.log10(hi['gain_1k']/lo['gain_1k']))
    results['assumptions']=['Ideal regulated B+ in audio runs; separate supply simulation required','16/18 ohm constant resistors do not model actual earphone impedance curves','No tube intrinsic noise or validated thermal dynamics','Model discrepancy prevents predictive signoff']
    (ROOT/'results/audio.json').write_text(json.dumps(results,indent=2)+'\n')
    ax[0].set(xlim=(10,100000),ylim=(-3,1),xlabel='Frequency (Hz)',ylabel='Relative gain (dB)',title='High mode frequency response');ax[0].legend()
    ax[1].set(xlabel='Frequency (Hz)',ylabel='Output impedance (ohm)',title='Driving point output impedance')
    for a in ax:a.grid(alpha=.25,which='both')
    fig.tight_layout();fig.savefig(ROOT/'results/audio_response.png',dpi=180)
    print(json.dumps({k:results[k] for k in ['nominal','zout_ohm','distortion']},indent=2))

if __name__=='__main__':main()
