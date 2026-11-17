from pathlib import Path
import json,zlib
ROOT=Path(__file__).resolve().parent.parent;CLIENT=ROOT/'client/Requiem Aurakingdom'
manifest=json.loads((ROOT/'docs/map-compatibility-manifest.json').read_text())
archive={x['name'].split('/',1)[1].lower():x for x in json.loads((ROOT/'docs/v15-original-archive.json').read_text())['files']}
out=[]
for relative in sorted({s['model'] for s in manifest['scenes']}):
 path=CLIENT/relative;ref=archive.get(relative.lower());crc=0
 with path.open('rb') as f:
  while chunk:=f.read(1024*1024):crc=zlib.crc32(chunk,crc)
 crc=f'{crc:08x}';out.append({'path':relative,'crc':crc,'original_crc':ref['crc'] if ref else None,'matches_original':crc==ref['crc'] if ref else None})
(ROOT/'docs/map-geometry-validation.json').write_text(json.dumps(out,indent=2))
print(json.dumps({'models_checked':len(out),'original_matches':sum(x['matches_original'] is True for x in out),'mismatches':[x for x in out if x['matches_original'] is False],'no_original_reference':[x for x in out if x['matches_original'] is None]},indent=2))
