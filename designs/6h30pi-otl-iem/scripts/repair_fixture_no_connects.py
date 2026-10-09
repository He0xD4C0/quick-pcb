"""Mark only the 16 intentionally unused fixture pins; never apply to the amplifier."""
import json
from eda_session import R, session, PROJECT, _state
from boardspec_mcp.schematic_tools import set_schematic_no_connects, get_schematic_violations
b,w=session();s,_,error=_state(b,w);assert not error,error
assert s['source']['project_uuid']==PROJECT and s['source']['page_uuid']=='f46a303398832651'
# Deliberately connected pins: R1.1/J1.3 and R1.2/V1.6. Everything else
# on this library-only fixture is deliberately unused.
connected={('R1','1'),('J1','3'),('R1','2'),('V1','6')}
edits=[{'designator':'V1','pin_selectors':['#1','#2','#3','#4','#5','#7','#8','#9']},
       {'designator':'J1','pin_selectors':['#1','#2']},
       {'designator':'RV1','pin_selectors':['#1','#2','#3','#4','#5','#6']}]
assert not any((e['designator'],p[1:]) in connected for e in edits for p in e['pin_selectors'])
result=set_schematic_no_connects(b,w,s['context_revision'],s['revision'],edits)
(R/'evidence/eda/fixture-no-connect-repair.json').write_text(json.dumps(result,indent=2)+'\n')
assert result.get('ok'),result
after,_,error=_state(b,w);assert not error,error
assert len(after['no_connects'])==16,after['no_connects']
assert not any((p['designator'],p['pin'].lstrip('#')) in connected for p in after['no_connects'])
drc=get_schematic_violations(b,w)
(R/'evidence/eda/fixture-drc-detailed-after-repair.json').write_text(json.dumps(drc,indent=2)+'\n')
print(json.dumps({'nc':len(after['no_connects']),'passed':drc.get('passed'),'violations':drc.get('violations')},indent=2))
