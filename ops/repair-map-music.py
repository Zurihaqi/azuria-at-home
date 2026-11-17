from pathlib import Path
import hashlib,json,re,shutil
root=Path(__file__).resolve().parent.parent
client=root/'client/Requiem Aurakingdom'
report=json.loads((root/'docs/official-music-report.json').read_text())
for item in report['downloaded']:
 source=root/'downloads/music'/(item['name']+'.ogg');target=client/'bgm'/source.name
 assert hashlib.sha256(source.read_bytes()).hexdigest()==item['sha256']
 if not target.exists():shutil.copy2(source,target)
def records(data):
 return {int(r[0]):r for ch in re.split(r'(?m)(?=^[0-9]+\|)',data.decode('cp950',errors='strict'))[1:] if len(r:=ch.rstrip().split('|'))==68}
target=client/'data/db/C_Node.ini';original=target.read_bytes()
backup=root/'private/client-original/C_Node.pre-music-fix.ini'
if not backup.exists():backup.write_bytes(original)
server=records((root/'staging/ultimate/hxsy/Data/db/S_Node.ini').read_bytes())
# Tracks absent from the official 2023 installer use existing related-zone music.
fallback={'bgm047':'bgm046','bgm048':'bgm043','bgm134':'bgm133','bgm135':'bgm132','bgm406':'bgm405','bgmcabal':'bgm017'}
changes=[]
def replace(match):
 chunk=match.group();row=chunk.rstrip().split('|');ident=int(row[0])
 if len(row)!=68 or ident not in server:return chunk
 desired=[fallback.get(x,x) for x in server[ident][14:18]]
 for x in desired:assert not x or (client/'bgm'/(x+'.ogg')).is_file(),(ident,x)
 if desired!=row[14:18]:
  changes.append({'node':ident,'before':row[14:18],'after':desired});row[14:18]=desired
  return '|'.join(row)+'\r\n'
 return chunk
text=original.decode('cp950');pattern=r'(?ms)^[0-9]+\|.*?(?=^[0-9]+\||\Z)'
updated=re.sub(pattern,replace,text).encode('cp950')
before=records(original);after=records(updated)
assert before.keys()==after.keys()
for i in before:assert before[i][:14]==after[i][:14] and before[i][18:]==after[i][18:]
target.chmod(0o666)
with target.open('r+b') as f:f.write(updated);f.truncate()
out={'original_tracks_restored':len(report['downloaded']),'map_rows_repaired':len(changes),'fallbacks':fallback,'changed_fields':'Only map music/ambient references (columns 14..17)','map_changes':changes,'backup':str(backup),'sha256':hashlib.sha256(updated).hexdigest(),'validation':'All changed map audio references exist; every non-audio map field unchanged. In-game transitions pending.'}
(root/'docs/music-repair-report.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:v for k,v in out.items() if k!='map_changes'},indent=2))
