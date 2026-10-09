#!/usr/bin/env python3
"""Download explicit manufacturer documents, checking PDF magic and hashes."""
from pathlib import Path
import urllib.request,json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'evidence/datasheets'
sources={
 '6H30Pi-EB.pdf':'https://shop.ehx.com/catalog/tubes-specs/6H30Pi-EB.pdf',
 'nichicon-LLS.pdf':'https://www.nichicon.co.jp/english/series_items/catalog_pdf/e-lls.pdf',
 'PJ-301C.pdf':'https://jlcpcb.com/api/file/downloadByFileSystemAccessId/8588896494385057792',
 'MPSA42.pdf':'https://www.onsemi.com/download/data-sheet/pdf/mpsa42-d.pdf',
 'LM1084.pdf':'https://www.ti.com/lit/ds/symlink/lm1084.pdf',
 'IRF820.pdf':'https://www.vishay.com/docs/91059/91059.pdf',
 'ALPS-RK097.pdf':'https://tech.alpsalpine.com/cms.media/product_catalog_rv_01_rk097_en_d953249ce7.pdf',
 'IXTH30N50L2.pdf':'https://www.littelfuse.com/assetdocs/littelfuse-discrete-mosfets-ixt-30n50-datasheet?assetguid=c09539a4-39f7-4fb5-940f-2103ab4fa891',
 'panasonic-FR.pdf':'https://industrial.panasonic.com/cdbs/www-data/pdf/RDF0000/ABA0000C1259.pdf',
 'pickering-67.pdf':'https://www.pickeringrelay.com/pdfs/67-68-high-voltage-reed-relays.pdf',
 'eaton-HTC.pdf':'https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-htc-fuse-holder.pdf',
 'schurter-6100.pdf':'https://catalogue.schurter.com/en/datasheet/typ_6100-3.pdf',
 'MJE340.pdf':'https://www.onsemi.com/download/data-sheet/pdf/mje340-d.pdf',
 'BU508A.pdf':'https://www.st.com/resource/en/datasheet/bu508a.pdf',
 'omron-G2R.pdf':'https://components.omron.com/sites/default/files/datasheet_pdf/K013-E1.pdf',
}
index=json.loads((out/'index.json').read_text()) if (out/'index.json').exists() else {}
for n,url in sources.items():
 if (out/n).exists() and (out/n).read_bytes().startswith(b'%PDF'):
  continue
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
  with urllib.request.urlopen(req,timeout=30) as resp:data=resp.read();final=resp.url
  if not data.startswith(b'%PDF'):raise ValueError('Response is not PDF')
  (out/n).write_bytes(data);index[n]={'url':url,'resolved_url':final,'sha256':hashlib.sha256(data).hexdigest(),'status':'downloaded'};print(n,len(data),flush=True)
 except Exception as e:index[n]={'url':url,'status':'download_failed','error':str(e)};print(n,type(e).__name__,str(e),flush=True)
 (out/'index.json').write_text(json.dumps(index,indent=2)+'\n')
