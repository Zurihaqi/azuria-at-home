"""Stage authoritative scene/collision data, auditing every referenced render asset."""
from pathlib import Path,PurePosixPath
import hashlib,json,re,tarfile,zlib
ROOT=Path(__file__).resolve().parent.parent;CLIENT=ROOT/'client/Requiem Aurakingdom'
SOURCE=ROOT/'staging/map-compatibility';SOURCE.mkdir(exist_ok=True)
ARCHIVE=ROOT/'downloads/map-compat-source.tar.gz'
expected={x['name'].split('/',1)[1].lower():x for x in json.loads((ROOT/'docs/v15-original-archive.json').read_text())['files']}
def sha(raw):return hashlib.sha256(raw).hexdigest()
with tarfile.open(ARCHIVE,'r:gz') as tar:
 for member in tar:
  path=PurePosixPath(member.name)
  if member.isdir():continue
  assert member.isfile() and len(path.parts)==2 and path.parts[0] in ['scene','NodeMap'],member.name
  assert re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*\.(ini|csm|pgp|smp|fsmp|ssmp)',path.name,re.I),member.name
  dest=SOURCE.joinpath(*path.parts);dest.parent.mkdir(exist_ok=True);dest.write_bytes(tar.extractfile(member).read())
def geometry(raw):
 lines=raw.splitlines()
 for i,line in enumerate(lines):
  if line.strip().lower()==b'[globe_data],':return lines[i+1].decode('ascii').split(',')
 raise ValueError('No globe_data')
manifest={'source_sha256':sha(ARCHIVE.read_bytes()),'files':[],'scenes':[],'missing_models':[],'available_original_copies':[],'missing_collision':[]}
for source in sorted((SOURCE/'scene').glob('*.ini')):
 row=geometry(source.read_bytes());model=row[0];stem=Path(model).stem
 assert re.fullmatch(r'[A-Za-z0-9_-]+\.(nif|fsm)',model,re.I),(source.name,row)
 relative=f'map/model/{stem}/{model}';target=CLIENT/relative
 entry={'scene':source.name,'geometry':','.join(row),'model':relative,'model_present':target.exists()}
 if not target.exists():
  original=ROOT/'client/Aura Kingdom V15 Clean'/relative;ref=expected.get(relative.lower())
  if original.exists() and ref and f'{zlib.crc32(original.read_bytes()):08x}'==ref['crc']:
   manifest['available_original_copies'].append({'path':relative,'source':str(original),'sha256':sha(original.read_bytes())});entry['model_present']=True
  else:manifest['missing_models'].append(entry.copy())
 for asset in [row[4],stem+'.pgp']:
  if not (CLIENT/'map/sknodemap'/asset).exists() and not (SOURCE/'NodeMap'/asset).exists():manifest['missing_collision'].append({'scene':source.name,'asset':asset})
 old=CLIENT/'data/scene'/source.name
 entry['previous_geometry']=','.join(geometry(old.read_bytes())) if old.exists() else None
 entry['geometry_changed']=entry['previous_geometry']!=entry['geometry']
 ref=expected.get(('data/scene/'+source.name).lower());entry['matches_original_zip']=f'{zlib.crc32(source.read_bytes()):08x}'==ref['crc'] if ref else None
 manifest['scenes'].append(entry)
for directory,targetdir in [('scene','data/scene'),('NodeMap','map/sknodemap')]:
 for source in sorted((SOURCE/directory).iterdir()):
  target=CLIENT/targetdir/source.name;raw=source.read_bytes();before=sha(target.read_bytes()) if target.exists() else None
  if before==sha(raw):continue
  relative=targetdir+'/'+source.name;ref=expected.get(relative.lower());crc=f'{zlib.crc32(raw):08x}'
  manifest['files'].append({'target':relative,'source':str(source),'before_sha256':before,'after_sha256':sha(raw),'bytes':len(raw),'original_zip_crc':ref['crc'] if ref else None,'source_crc':crc,'matches_original_zip':crc==ref['crc'] if ref else None})
(ROOT/'docs/map-compatibility-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'scene_count':len(manifest['scenes']),'files_to_change':len(manifest['files']),'changed_bytes':sum(x['bytes'] for x in manifest['files']),'geometry_changes':sum(x['geometry_changed'] for x in manifest['scenes']),'missing_models':manifest['missing_models'],'missing_collision_count':len(manifest['missing_collision']),'original_scene_crc_matches':sum(x['matches_original_zip'] is True for x in manifest['scenes'])},indent=2))
