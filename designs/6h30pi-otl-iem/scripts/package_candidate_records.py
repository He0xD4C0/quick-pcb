#!/usr/bin/env python3
import json,csv,hashlib,datetime,shutil,zipfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'delivery';B=json.loads((R/'topology-candidate.json').read_text());L=json.loads((R/'parts.lock.json').read_text())['parts'];A=json.loads((R/'parts.audit.json').read_text())['reviews'];E=json.loads((R/'parts.exceptions.json').read_text())['parts'];S=json.loads((R/'evidence/eda/candidate-final-state.json').read_text());byref={p['ref']:p for p in B['parts']}
# Separate raw imported library IDs from actual project-remapped IDs.
bindings=[]
for c in S['components']:
 p=byref[c['designator']];z=L.get(p['key'],{})
 bindings.append({'reference':c['designator'],'alias':p['alias'],'part':c['sub_part_name'],'physical_key':p['key'],'supplier_id':z.get('lcsc'),'original_device_uuid':z.get('device_uuid'),'actual_project_device':c['component'],'actual_project_symbol':c['symbol'],'actual_project_footprint':c['footprint'],'actual_pin_numbers':[p['number'] for p in c['pins']]})
(D/'native-bindings.json').write_text(json.dumps(bindings,indent=2,ensure_ascii=False)+'\n')
newreviews={
 'aux_npn_bd139':{'mpn':'BD13910S','physical_pin_functions':{'1':'emitter','2':'collector / tab','3':'base'},'source':'evidence/datasheets/onsemi-bd139.pdf p1,4','source_url':'https://www.onsemi.com/download/data-sheet/pdf/bd139-d.pdf','sha256':hashlib.sha256((R/'evidence/datasheets/onsemi-bd139.pdf').read_bytes()).hexdigest(),'pin_review':'DOCUMENT_REVIEWED','ratings':{'VCEO_V':80,'IC_A':1.5,'PC_W_TA25':1.25,'PC_W_TC25':12.5},'application_review':'NOT_QUALIFIED'},
 'fault_opto':{'mpn':'LTV-817S-TA1-C','physical_pin_functions':{'1':'LED anode','2':'LED cathode','3':'phototransistor emitter','4':'phototransistor collector'},'source':'evidence/datasheets/liteon-ltv8x7.pdf printed pp2,5,9-10; manufacturer document archived from distributor mirror, Revision K2010','source_url':'https://www.dena-de.com/uploads/shop/recursos/LTV-8x7_Series.pdf','sha256':hashlib.sha256((R/'evidence/datasheets/liteon-ltv8x7.pdf').read_bytes()).hexdigest(),'pin_review':'DOCUMENT_REVIEWED','ratings':{'IF_mA':50,'VCEO_V':35,'IC_mA':50},'application_review':'CTR at the low detector current and fault cutoff timing NOT_QUALIFIED'}
}
(R/'completion-sources.json').write_text(json.dumps(newreviews,indent=2)+'\n')
# This declares an explicit schematic electrical classification, not physical approval.
types={}
for key in sorted({p['key'] for p in B['parts']}):
 z=L.get(key,E.get(key,{}));raw={p['number']:p.get('raw_type') for p in z.get('pins',[])}
 types[key]={'native_library_types_unchanged':raw,'boardspec_types':{'1':'input','2':'power_out','3':'power_in'} if key=='heater_ldo' else 'passive analog terminals','reason':'Resistors, capacitors, contacts and discrete analog semiconductor terminals are modeled as passive connection points; LM1084 supply direction is explicit. No native library type was rewritten.','pin_review':A.get(key,newreviews.get(key,{})).get('pin_review',E.get(key,{}).get('review_status','UNCONFIRMED')),'physical_and_application_gate':'See parts.audit.json / parts.exceptions.json; not implied by BoardSpec validation'}
(D/'electrical-type-review.json').write_text(json.dumps(types,indent=2,ensure_ascii=False)+'\n')
with (D/'BOM.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Reference','Alias','Manufacturer','MPN','LCSC','Value','Ratings','Raw_pin_types','Datasheet_or_evidence','Application_status'])
 for p in B['parts']:
  k=p['key'];z=L.get(k,E.get(k,{}));review=A.get(k,newreviews.get(k,{}));w.writerow([p['ref'],p['alias'],z.get('manufacturer','UNCONFIRMED CUSTOM'),z.get('mpn','QPCB-TX6H30-100VA-DRAFT'),z.get('lcsc',''),z.get('library_properties',{}).get('Value',''),json.dumps(review.get('ratings',z.get('ratings',{})),ensure_ascii=False),json.dumps({q['number']:q.get('raw_type') for q in z.get('pins',[])},ensure_ascii=False),json.dumps(review.get('sources',review.get('source',z.get('sources',[]))),ensure_ascii=False),'CANDIDATE / NOT QUALIFIED'])
for file in ['boardspec.yaml','parts.lock.json','parts.audit.json','parts.exceptions.json','reference-map.json','completion-sources.json']:
 shutil.copy2(R/file,D/file)
shutil.copy2(R/'simulation/audio-results.json',D/'audio-results.json');shutil.copy2(R/'evidence/eda/candidate-final-connection-check.json',D/'connection-check.json');shutil.copy2(R/'evidence/boardspec-validation.json',D/'boardspec-validation.json')
checkpoint=json.loads((D/'checkpoint.json').read_text());checkpoint['connection_check']='PASS_NATIVE_GEOMETRY_AND_PIN_READBACK';checkpoint['manufacturing_netlist_check']='BLOCKED_NATIVE_DRC';(D/'checkpoint.json').write_text(json.dumps(checkpoint,indent=2)+'\n')
status={'captured_at':datetime.datetime.now().astimezone().isoformat(),'stage':'ONE_SHEET_CANDIDATE_DELIVERED','task_complete':False,'drawing_delivered':True,'full_schematic':'NATIVE_SAVED_REOPENED_EXPORTED_ONE_PAGE','physical_components':138,'net_count':79,'parts_gate':'NOT_PASSED_CUSTOM_TRANSFORMER_AND_FOOTPRINTS_UNCONFIRMED','topology_geometry_check':'PASS','native_manufacturing_netlist':'BLOCKED_BY_DRC','native_drc':checkpoint['native_drc'],'simulation_acceptance':'NOT_PASSED_AUDIO_NOMINAL_ONLY','physical_testing':'NOT_PERFORMED','delivery':'delivery/6H30Pi-Stereo-CANDIDATE.eprj2','portable_delivery':'delivery/6H30Pi-Stereo-CANDIDATE.epro2','Codex_restarted':False,'remaining':['Native custom footprints: V1,V2,K1,K2,J3,SW2,T1','Transformer terminal numbers are proposed contract, not a confirmed physical drawing','Output capacitor leakage bound24/27mV exceeds2mV target','Whole power supply, faults, tolerance, noise and thermal acceptance not established','Tube model cross-curve mismatch46.70% limits THD claims'],'checkpoint':checkpoint}
(R/'status.json').write_text(json.dumps(status,indent=2)+'\n');print('packaged records',len(bindings),'units;',len(types),'part types')
