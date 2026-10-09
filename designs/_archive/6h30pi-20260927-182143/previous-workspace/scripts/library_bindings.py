"""Exact EasyEDA library bindings; semantic terminals map to library pin numbers.
Preserve original symbol/device/footprint UUIDs and electrical pin types.
Selection is schematic sourcing, not a completed purchasing qualification.
"""
from pathlib import Path
import json,collections,copy,zipfile,hashlib
ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/'results/library'
SELECTED=json.loads((LIB/'selected.json').read_text())
def parse_documents(text):
 docs={};current=None
 for line in text.splitlines():
  line=line.rstrip('|')
  if '||' not in line:continue
  h,v=map(json.loads,line.split('||',1))
  if h['type']=='DOCHEAD':
   current=docs.setdefault(v['uuid'],{'head':(h,v),'rows':{}})
  elif current is not None:current['rows'][(h['type'],h.get('id'))]=(h,v)
 return docs

def select(c):
 t=c['type'];v=c['value'];a=c['alias']
 if t=='R':return 'R'
 if t=='C':return 'CP' if 'electrolytic' in c['rating'] or a in ['CHV1','CHV2','CHF','CAUX'] else 'C'
 if t=='D':return v if v in SELECTED else 'Z'
 if t in ['MOS','NPN','LDO','TP']:return t
 if t=='LINK' and a.startswith('F'):return 'F'
 return None

def binding(c):
 key=select(c)
 if key is None:return None
 z=SELECTED[key];it=z['item'];pins=z['pins'];mapping={n:n for n in c['pins']}
 if c['type']=='D':
  if key=='1N4148':mapping={'A':'2','K':'1'} # exported symbol triangle points LEFT, cathode bar at x=-5
  elif key=='Z':mapping={'A':'1','K':'2'} # official generic zener bar at x=+10
  else:
   mapping={}
   for p in pins:
    if p['name']=='A':mapping['A']=p['number']
    if p['name'] in ['K','C']:mapping['K']=p['number']
   assert set(mapping)=={'A','K'},(key,pins)
 assert set(mapping.values())=={p['number'] for p in pins},(c['alias'],mapping,pins)
 props=copy.deepcopy(it.get('otherProperty',{})) if z['kind']=='device' else {}
 sym=it['symbolUuid'] if z['kind']=='device' else it['uuid']
 props.update(Symbol=sym,Name=c['value'])
 # A generic symbol is not a purchasing SKU. In particular CP's source symbol title
 # mentions a package; do NOT assign that package to any capacitor.
 if z['kind']=='symbol':props.update({'Footprint':'','Convert to PCB':'no'})
 return dict(key=key,kind=z['kind'],item=it,pins=pins,mapping=mapping,symbol=sym,
             device=it['uuid'] if z['kind']=='device' else hashlib.sha256(('6h30-generic-library:'+sym).encode()).hexdigest()[:16],part=pins[0]['part'],properties=props)

def documents(keys):
 all_docs={}
 for key in sorted(set(keys)):
  for uuid,d in parse_documents((LIB/(key.replace(' ','_')+'-full.elibu')).read_text()).items():
   all_docs[uuid]=d
  with zipfile.ZipFile(LIB/(key.replace(' ','_')+'-full.elibz2')) as z:
   if 'device2.json' in z.namelist():
    for uuid,dev in json.loads(z.read('device2.json'))['devices'].items():
     all_docs[uuid]={'head':({'type':'DOCHEAD'},{'docType':'DEVICE','uuid':uuid,'editVersion':'3.2.186'}),'rows':{('META','META'):({'type':'META','id':'META','ticket':1},{'title':dev['display_title'],'attributes':dev['attributes'],'description':dev.get('description',''),'source':dev['path']})}}
  if SELECTED[key]['kind']=='symbol' and key!='NET':
   item=SELECTED[key]['item'];uuid=hashlib.sha256(('6h30-generic-library:'+item['uuid']).encode()).hexdigest()[:16]
   all_docs[uuid]={'head':({'type':'DOCHEAD'},{'docType':'DEVICE','uuid':uuid,'editVersion':'3.2.186'}),'rows':{('META','META'):({'type':'META','id':'META','ticket':1},{'title':item['name']+' (generic, purchasing TBD)','attributes':{'Symbol':item['uuid'],'Footprint':'','Add into BOM':'yes','Convert to PCB':'no','Name':item['name'],'Designator':'X?'},'description':'Project wrapper using unmodified official EasyEDA library symbol; no purchasing SKU or footprint selected.'})}}
 return all_docs
