#!/usr/bin/env python3
"""Component-level bounds, not full-amplifier simulations or acceptance."""
import json,itertools,math
from pathlib import Path
R=Path(__file__).resolve().parents[1];a=json.loads((R/'parts.audit.json').read_text())['reviews']
def parallel(x,y):return 1/(1/x+1/y)
def gains(rs,rsh,pot,volume,source,grid):
 bottom=parallel(pot*volume,grid);branch=pot*(1-volume)+bottom;tap=bottom/branch
 hi_load=parallel(branch,rs+rsh)
 hi=hi_load/(source+hi_load)*tap
 low_load=parallel(rsh,branch)
 lo=low_load/(source+rs+low_load)*tap
 return hi,lo
corners=[]
for rs,rsh,pot,volume,source in itertools.product([8200*.99,8200*1.01],[1000*.99,1000*1.01],[8000,12000],[.01,.1,.5,1],[0,100]):
 hi,lo=gains(rs,rsh,pot,volume,source,110000)
 corners.append({'rs_ohm':rs,'rsh_ohm':rsh,'pot_ohm':pot,'electrical_volume_fraction':volume,'source_ohm':source,'high_to_low_dB':20*math.log10(hi/lo)})
lo=min(corners,key=lambda x:x['high_to_low_dB']);hi=max(corners,key=lambda x:x['high_to_low_dB'])
leak=a['c_output_1000u250']['ratings']['leakage_A_max_at20C_5min']
out={'scope':'COMPONENT_PREFLIGHT_ONLY; no full topology generated or amplifier acceptance claimed',
 'input_mode_network':{'candidate':'8.2k series /1k shunt, selected node feeds dual10k pot; alternate position bypasses series resistor','grid_load_assumption_ohm':110000,'source_impedance_range_ohm':[0,100],'volume_zero_excluded':'Both modes have zero output; ratio is undefined','corners':len(corners),'minimum':lo,'maximum':hi,'within_20_plusminus_0p5_db':19.5<=lo['high_to_low_dB'] and hi['high_to_low_dB']<=20.5,'limitations':['This is a loaded passive-network bound at midband, not the actual WCF gain','Switch bounce, DC across input coupling capacitor, source limits and frequency response not included']},
 'output_electrolytic_leakage':{'part':'LLS2E102MELB','datasheet_max_A':leak,'test_condition':'20C, rated250V, after5min; conservative allowed-current scenario, not predicted90V leakage','loads':[{'ohm':load,'voltage_V':leak*load,'required_current_A_max':.002/load,'guarantees_2mV':leak*load<=.002} for load in [16,18]],'resolution':'Need a qualified lower-leakage part/network or measured binning with explicit limits; cannot assert specification compliance from a typical sample'},
 'heater_reservoir':{'part':'EEUFR1E332','conservative_100Hz_ripple_A':a['c_heater_3300u25']['ratings']['ripple_A_100Hz_conservative'],'note':'Ripple-current capability is not DC output current. Rectifier pulse/RMS test remains required.'},
 'rejected_film':{'part':'MKP1848720454Y5','reason':'Manufacturer6 pins; library4 pins/pads; not eligible for physical topology'},
 'status':{'schematic_acceptance':'NOT_PERFORMED','full_simulation_acceptance':'NOT_PERFORMED','hardware':'NOT_PERFORMED'}}
(R/'results/component-preflight.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
