from pathlib import Path
import datetime,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent.parent
manifest=json.loads((ROOT/'docs/set-pen-manifest.json').read_text())
entries=[x for x in manifest['files'] if not x['name'].startswith('S_')]
client=ROOT/'client/Requiem Aurakingdom/data/db';payload=ROOT/'staging/pen-upgrade'
for entry in entries:
 assert hashlib.sha256((client/entry['name']).read_bytes()).hexdigest()==entry['before_sha256']
 assert hashlib.sha256((payload/entry['name']).read_bytes()).hexdigest()==entry['after_sha256']
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=ROOT/'private/client-original'/('set-pen-'+stamp);backup.mkdir()
for entry in entries:shutil.copy2(client/entry['name'],backup/entry['name'])
try:
 for entry in entries:
  with (client/entry['name']).open('r+b') as out:out.write((payload/entry['name']).read_bytes());out.truncate()
except Exception:
 for entry in entries:shutil.copy2(backup/entry['name'],client/entry['name'])
 raise
(ROOT/'docs/set-pen-client-report.json').write_text(json.dumps(dict(backup=str(backup),files=[e['name'] for e in entries]),indent=2))
print('Updated four client tables; backup saved at '+str(backup))
