#!/usr/bin/env python3
"""Produce explicit incomplete-stage status and a candidate-type CSV, not a BOM."""
import json,csv,hashlib,datetime
from pathlib import Path
R=Path(__file__).resolve().parents[1]
l=json.loads((R/'parts.lock.json').read_text());a=json.loads((R/'parts.audit.json').read_text())['reviews']
for k,p in l['parts'].items():assert hashlib.sha256((R/p['archive']).read_bytes()).hexdigest()==p['archive_sha256'],k
with (R/'parts-candidates.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['candidate_key','manufacturer','MPN','LCSC','device_uuid','symbol_uuid','footprint_uuid','review_status','purpose'])
 for k,p in l['parts'].items():w.writerow([k,p['manufacturer'],p['mpn'],p['lcsc'],p['device_uuid'],p['symbol_uuid'],p['footprint_uuid'],p['review']['status'],p['intended_role']])
gate={'captured_at':datetime.datetime.now().astimezone().isoformat(),'stage':'PARTS_AND_MINIMAL_LOADING','task_complete':False,'cleanup':'ARCHIVE_HASHES_AND_RESTORE_VERIFIED','parts':{'candidate_types':len(l['parts']),'document_reviewed_types':sum(v['pin_review']=='DOCUMENT_REVIEWED' for v in a.values()),'rejected_types':[k for k,v in a.items() if v['pin_review'].startswith('REJECTED')],'not_yet_document_reviewed':[k for k in l['parts'] if k not in a],'source_archive_hashes_verified':True,'all_instances_bound':'NOT_APPLICABLE_NO_FINAL_INSTANCES_YET','passed':False},'minimal_native_load':json.loads((R/'evidence/eda/fixture-checkpoint.json').read_text()),'full_topology':'NOT_GENERATED','full_schematic':'NOT_DRAWN','simulation_acceptance':'NOT_PERFORMED','physical_testing':'NOT_PERFORMED','blockers':['Native diagnostics now available: custom tube units lack a verified socket footprint (3 fatal errors and 1 pin/pad error); native exporter aborts its preflight. No user screenshot needed.','Output isolation capacitance/leakage selection unresolved;200uFfilm library rejected for physical-pin mismatch.','Custom transformer physical terminal drawing and socket electrical ratings remain unconfirmed.'],'runtime_fix':{'file':'mcp-server/boardspec_mcp/schematic_drc.py','change':'Capture EasyEDA3.2 DRC log details, reject empty netlists, and resolve No Connect pins across multi-part devices','verification':'122 MCP tests passed; native save/reopen confirmed16 No Connect flags and zero floating-pin warnings','scope':'repository implementation used by this task; no plugin reinstall or Codex restart'}}
(R/'status.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'types':gate['parts'],'task_complete':False},ensure_ascii=False,indent=2))
