"""Interim repair while the full release client is unavailable due MEGA quota."""
from pathlib import Path
import datetime,hashlib,json,re,shutil,zlib
ROOT=Path(__file__).resolve().parent.parent
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db'
SOURCE=ROOT/'staging/v15-original/Aura Kingdom v15 Unpacked/data/db'
manifest=json.loads((ROOT/'docs/v15-original-archive.json').read_text())
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=ROOT/'private/client-original'/('quest-display-'+stamp);backup.mkdir()
changed=[]
for name in ['C_Mission.ini','T_Mission.ini']:
 source=next(p for p in SOURCE.iterdir() if p.name.lower()==name.lower())
 expected=next(e for e in manifest['files'] if e['name'].lower().endswith('/data/db/'+name.lower()))
 data=source.read_bytes()
 assert len(data)==expected['size'] and f'{zlib.crc32(data)&0xffffffff:08x}'==expected['crc']
 target=CLIENT/name;shutil.copy2(target,backup/name)
 with target.open('r+b') as out:out.write(data);out.truncate()
 changed.append(dict(file=name,source='Matching V15 release ZIP; CRC verified',sha256=hashlib.sha256(data).hexdigest()))

def records(path):
 return {int(row[0]):row for chunk in re.split(r'(?m)(?=^\d+\|)',path.read_bytes().decode('cp950'))[1:] if len(row:=chunk.rstrip('\r\n').split('|'))==74}
server=records(ROOT/'staging/ultimate/hxsy/Data/db/S_Level.ini')
path=CLIENT/'C_Level.ini';before=path.read_bytes();client=records(path)
text=before.decode('cp950');chunks=re.split(r'(?m)(?=^\d+\|)',text)
updates=0
for i in range(1,len(chunks)):
 raw=chunks[i];line=raw.rstrip('\r\n').split('|');ident=int(line[0])
 if ident in server and len(line)==74:
  original=line.copy()
  for field in [1,33]:line[field]=server[ident][field]
  if line!=original:updates+=1
  chunks[i]='|'.join(line)+'\r\n'
updated=''.join(chunks).encode('cp950');shutil.copy2(path,backup/path.name)
with path.open('r+b') as out:out.write(updated);out.truncate()
after=records(path)
for ident,row in client.items():
 assert all(row[i]==after[ident][i] for i in range(74) if i not in [1,33])
assert after[100][1]=='1002435750'
report=dict(backup=str(backup),restored=changed,level_exp_rows_aligned=updates,level_exp_columns=[1,33],
 full_clean_reset=False,full_reset_blocker='MEGA bandwidth limit; separate clean build remains incomplete',
 character_progress='Untouched by this client repair')
(ROOT/'docs/quest-display-repair.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
