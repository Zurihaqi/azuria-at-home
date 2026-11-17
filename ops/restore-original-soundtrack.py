from pathlib import Path
import hashlib,json,shutil
root=Path(__file__).resolve().parent.parent
source=root/'downloads/music';target=root/'client/Requiem Aurakingdom/bgm'
report=json.loads((root/'docs/official-music-full-report.json').read_text())
assert len(report['downloaded'])==153 and not report['failed'] and not report['unavailable']
backup=root/'private/client-original/bgm-pre-official-restore';backup.mkdir(parents=True,exist_ok=True)
changed=[];added=[];same=[]
for item in report['downloaded']:
 name=item['name']+'.ogg';assert Path(name).name==name
 data=(source/name).read_bytes();assert hashlib.sha256(data).hexdigest()==item['sha256'] and data.startswith(b'OggS')
 dest=target/name
 if dest.exists():
  oldhash=hashlib.sha256(dest.read_bytes()).hexdigest()
  if oldhash==item['sha256']:same.append(name);continue
  saved=backup/name
  if not saved.exists():shutil.copy2(dest,saved)
  changed.append({'name':name,'original_client_sha256':oldhash,'official_sha256':item['sha256']})
 else:added.append(name)
 shutil.copy2(source/name,dest)
for item in report['downloaded']:
 assert hashlib.sha256((target/(item['name']+'.ogg')).read_bytes()).hexdigest()==item['sha256']
result={'official_source':report['source'],'verified_official_files':153,'replaced_files':changed,'added_files':added,'already_original':same,'backup':str(backup),'validation':'Every installed official soundtrack file matches the checksummed original installer output; gameplay listening test pending.','later_map_fallbacks':json.loads((root/'docs/music-repair-report.json').read_text())['fallbacks']}
(root/'docs/full-soundtrack-restore.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'official_files_verified':153,'replaced':len(changed),'added':len(added),'already_original':len(same),'backup':str(backup)},indent=2))
