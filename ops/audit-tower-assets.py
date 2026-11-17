from pathlib import Path
import hashlib,json,zlib
ROOT=Path(__file__).resolve().parent.parent
manifest=json.loads((ROOT/'docs/v15-original-archive.json').read_text())['files']
expected={f['name'].split('/',1)[1].lower():f for f in manifest}
out=[]
for mapid in ['S703','S741']:
 for relative in [f'map/model/{mapid}/{mapid}.nif',f'map/model/{mapid}/{mapid}.ini',f'map/sknodemap/{mapid}.pgp',f'map/sknodemap/{mapid}.smp',f'map/sknodemap/{mapid}.fsmp']:
  path=ROOT/'client/Requiem Aurakingdom'/relative
  raw=path.read_bytes();crc=f'{zlib.crc32(raw):08x}';ref=expected.get(relative.lower())
  item={'path':relative,'size':len(raw),'crc':crc,'original_crc':ref.get('crc') if ref else None,'matches_original':crc==ref['crc'] if ref else None,'sha256':hashlib.sha256(raw).hexdigest()}
  if relative.endswith('.nif'):item['embedded_names']={s:raw.find(s.encode()) for s in ['S703','S741','s703','s741']}
  out.append(item)
print(json.dumps(out,indent=2));(ROOT/'docs/tower-floor3-assets.json').write_text(json.dumps(out,indent=2))
