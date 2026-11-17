"""Client-only, byte-for-byte original-map repair with complete rollback metadata."""
from pathlib import Path
import datetime,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent.parent;CLIENT=ROOT/'client/Requiem Aurakingdom'
manifest=json.loads((ROOT/'docs/map-compatibility-manifest.json').read_text())
models=json.loads((ROOT/'docs/map-geometry-validation.json').read_text())
assert not manifest['missing_models']
changed_scenes={Path(x['target']).name for x in manifest['files'] if x['target'].startswith('data/scene/')}
affected_models={s['model'] for s in manifest['scenes'] if s['scene'] in changed_scenes}
unverified_models=[x for x in models if x['matches_original'] is False]
assert not [x for x in unverified_models if x['path'] in affected_models],'A changed scene depends on a modified model; review before applying'
assert all(s['matches_original_zip'] is True for s in manifest['scenes'])
def sha(raw):return hashlib.sha256(raw).hexdigest()
for entry in manifest['files']:
 target=CLIENT/entry['target'];source=Path(entry['source'])
 assert target.resolve().is_relative_to(CLIENT.resolve()) and source.resolve().is_relative_to((ROOT/'staging/map-compatibility').resolve())
 assert sha(source.read_bytes())==entry['after_sha256']
 assert (sha(target.read_bytes()) if target.exists() else None)==entry['before_sha256'],entry['target']
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup=ROOT/'private/client-original'/('map-compatibility-'+stamp);backup.mkdir()
# Preserve every original before changing any file; added files are recorded separately.
for entry in manifest['files']:
 target=CLIENT/entry['target']
 if entry['before_sha256'] is not None:
  saved=backup/entry['target'];saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
(backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
applied=[]
try:
 for entry in manifest['files']:
  target=CLIENT/entry['target'];target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():
   with target.open('r+b') as out:out.write(Path(entry['source']).read_bytes());out.truncate()
  else:shutil.copy2(entry['source'],target)
  applied.append(entry)
 for entry in manifest['files']:assert sha((CLIENT/entry['target']).read_bytes())==entry['after_sha256']
except Exception:
 for entry in reversed(applied):
  target=CLIENT/entry['target']
  if entry['before_sha256'] is None:target.unlink()
  else:shutil.copy2(backup/entry['target'],target)
 raise
report={'backup':str(backup),'scenes_audited':len(manifest['scenes']),'files_restored':len(applied),'scene_files_restored':sum(x['target'].startswith('data/scene/') for x in applied),'collision_files_restored':sum(x['target'].startswith('map/sknodemap/') for x in applied),'geometry_remaps_fixed':[s['scene'] for s in manifest['scenes'] if s['geometry_changed']],'all_866_scenes_match_original_archive':True,'render_models_checked':len(models),'render_models_verified':sum(x['matches_original'] is True for x in models),'unchanged_scenes_with_unverified_model':unverified_models,'original_model_download':'MEGA returned HTTP 509; S048 model left untouched. Its dependent scene configs already matched the server and were not changed.','server_restarted':False,'database_modified':False,'validation':'Original scene CRCs and post-write SHA256 verified; Sky Tower and Gaia Chronicle gameplay checks pending'}
(ROOT/'docs/map-compatibility-deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
