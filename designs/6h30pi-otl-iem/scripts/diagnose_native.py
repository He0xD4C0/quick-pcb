"""Read live DRC details with the repository adapter, without touching rules."""
import json,datetime,hashlib
from pathlib import Path
from eda_session import session,R
from boardspec_mcp.schematic_bridge import run_strict_drc
from boardspec_mcp.schematic_drc import flatten_schematic_drc
b,w=session();raw=run_strict_drc(b,w);assert raw.get('ok'),raw
rows=flatten_schematic_drc(raw.get('result'))
report={'captured_at':datetime.datetime.now().astimezone().isoformat(),'window_id':w,
        'raw':raw,'passed':not rows,'violations':rows,
        'source_files':{}}
for path in [Path('/Applications/嘉立创EDA(专业版).app/Contents/Resources/app/assets/pro-ui/3.2.181.db96fbff/js/ui.js'),Path('/Applications/嘉立创EDA(专业版).app/Contents/Resources/app/assets/pro-sch/3.2.181.b4201c52/js/sch.js')]:
 report['source_files'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
(R/'evidence/eda/native-diagnosis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'violations':rows},indent=2))
