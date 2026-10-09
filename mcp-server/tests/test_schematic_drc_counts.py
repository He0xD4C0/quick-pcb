"""A real EasyEDA 3.2 response must not be normalized to a false pass."""
from boardspec_mcp.schematic_drc import flatten_schematic_drc


def test_native_severity_totals_remain_unresolved_violations():
    raw = [
        {"type": "fatalError", "count": 3},
        {"type": "error", "count": 1},
        {"type": "warn", "count": 1},
    ]
    rows = flatten_schematic_drc(raw, "test-page")
    assert len(rows) == 3
    assert sum(row["count"] for row in rows) == 5
    assert {row["severity"] for row in rows} == {"fatalError", "error", "warn"}
    assert all(row["type"] == "EDA_DRC_SUMMARY_ONLY" for row in rows)
    assert all(row["position"] is None and row["objects"] == [] for row in rows)


def test_zero_totals_do_not_create_violations():
    assert flatten_schematic_drc([{"type": "error", "count": 0}], "p") == []


def test_nested_totals_do_not_hide_detailed_errors():
    rows = flatten_schematic_drc({"totals": [{"type": "error", "count": 2}],
                                  "details": [{"errorType": "UNCONNECTED", "message": "R1.2"}]}, "p")
    assert {r["type"] for r in rows} == {"EDA_DRC_SUMMARY_ONLY", "UNCONNECTED"}


def test_real_32_log_capture_resolves_all_five_groups():
    import json
    from pathlib import Path
    # Frozen native event capture; independent of optional design workspace.
    raw = json.loads((Path(__file__).parent / 'fixtures/schematic_drc_32.json').read_text())
    rows = flatten_schematic_drc(raw, 'test-page')
    assert len(rows) == 5
    assert all(r['type'] == 'EDA_DRC_LOG' for r in rows)
    missing = [r for r in rows if r['severity'] == 'fatalError']
    assert {tuple(r['objects']) for r in missing} == {('component3',), ('component4',), ('component5',)}
    assert all('Footprint' in r['message'] and '<span' not in r['message'] for r in missing)
    floating = next(r for r in rows if r['severity'] == 'warn')
    assert len(floating['objects']) == 16
    assert 'V1.7' in floating['message'] and '{ObjectID}' not in floating['message']
    assert floating['page'] == 'f46a303398832651'


def test_partial_detail_capture_preserves_unexplained_count():
    raw = {'format': 'easyeda-drc-capture/v1',
           'result': [{'type': 'error', 'count': 2}],
           'logs': [{'type': 'error', 'tabType': 'schDrcLog', 'msg': 'One error'},
                    {'type': 'error', 'tabType': 'Log', 'msg': 'Unrelated'}]}
    rows = flatten_schematic_drc(raw)
    assert len(rows) == 2
    assert sum(r.get('count', 1) for r in rows) == 2
    assert not any(r['message'] == 'Unrelated' for r in rows)


def test_no_details_false_or_missing_must_not_pass():
    for result in (False, None):
        rows = flatten_schematic_drc({'format': 'easyeda-drc-capture/v1', 'result': result, 'logs': []})
        assert rows[0]['type'] == 'EDA_DRC_RESULT_UNAVAILABLE'


def test_newer_detailed_results_do_not_duplicate_log_mirror():
    rows = flatten_schematic_drc({'format': 'easyeda-drc-capture/v1',
        'result': [{'errorType': 'SHORT', 'message': 'short'}],
        'logs': [{'type': 'error', 'tabType': 'schDrcLog', 'msg': 'short'}]})
    assert len(rows) == 1 and rows[0]['type'] == 'SHORT'


def test_capture_subscription_removed_on_success_and_exception():
    import subprocess
    import json
    from boardspec_mcp.schematic_bridge import STRICT_DRC_JS
    script = '''const assert = require('node:assert/strict');
const check = new Function('eda', 'return (async()=>{' + CODE + '})()');
(async()=>{
 for (const fail of [false,true]) {
  let cb, cancelled=0;
  globalThis._MSG_BUS_={subscribe:(topic,fn)=>{cb=fn;return {cancel:()=>cancelled++}}};
  const eda={sch_Drc:{check:async()=>{cb({tabType:'schDrcLog',msg:'fixture'});if(fail)throw Error('native');return []}}};
  try { const r=await check(eda);assert.equal(r.logs.length,1);assert.equal(fail,false); }
  catch(e) { if(!fail)throw e;assert.equal(e.message,'native'); }
  assert.equal(cancelled,1);
 }
 delete globalThis._MSG_BUS_;
 assert.deepEqual((await check({sch_Drc:{check:async()=>[]}})).result,[]);
})().catch(e=>{console.error(e);process.exit(1)});'''.replace('CODE', json.dumps(STRICT_DRC_JS))
    subprocess.run(['node', '-e', script], check=True)


def test_multipart_no_connect_resolves_exact_physical_pin_and_rejects_ambiguity():
    import subprocess
    import json
    from boardspec_mcp.schematic_bridge import no_connect_program
    code = no_connect_program([{'designator': 'V1', 'pin_selectors': ['#1', '#9']}])
    script = '''const assert=require('node:assert/strict');
const run=new Function('eda','return (async()=>{'+CODE+'})()');
(async()=>{
 let written=[];
 const pin=n=>({getState_PinNumber:()=>n,getState_NoConnected:()=>false,
  toAsync:()=>({setState_NoConnected:()=>written.push(n),done:async()=>true})});
 const unit=pins=>({getState_Designator:()=>"V1",getAllPins:async()=>pins});
 const a=unit([pin("1")]),b=unit([pin("9")]);
 let parts=[a,b]; const eda={sch_PrimitiveComponent:{getAll:async()=>parts}};
 assert.equal((await run(eda)).every(r=>r.ok),true);
 assert.deepEqual(written,["1","9"]);
 written=[];parts=[a,b,unit([pin("9")])];
 const result=await run(eda);
 assert.equal(result[0].ok,false);assert.deepEqual(written,[]);
})().catch(e=>{console.error(e);process.exit(1)});'''.replace('CODE', json.dumps(code))
    subprocess.run(['node', '-e', script], check=True)
