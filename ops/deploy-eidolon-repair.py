"""Install reviewed Eidolon fixes while humans are offline; retain full rollback."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess as sp
os.umask(0o077)
source=Path('/tmp/eidolon-repair')
m=json.loads((source/'manifest.json').read_text())
drop=Path('/root/hxsy/Data/db/S_DropItem.ini')
binary=Path('/root/hxsy/ZoneServer/ZoneServer')
patch=m['skill_patch']
def sql(q):
    r=sp.run(['runuser','-u','postgres','--','psql','-X','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp',check=True)
    return r.stdout.strip()
assert sql('SELECT count(*) FROM player_characters WHERE quit=0 AND id NOT IN (50000002,50000003)')=='0','A human is online'
assert hashlib.sha256(drop.read_bytes()).hexdigest()==m['drops_before_sha256']
assert hashlib.sha256((source/drop.name).read_bytes()).hexdigest()==m['drops_after_sha256']
with binary.open('rb') as f:
    f.seek(patch['offset']);assert f.read(7)==bytes.fromhex(patch['before'])
backup=Path('/var/backups/aurakingdom')/('eidolon-repair-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
units=[u for u in ('ak-bot-awan','ak-bot-arden') if sp.run(['systemctl','is-active','--quiet',u]).returncode==0]
if units:sp.run(['systemctl','stop',*units],check=True,timeout=60)
sp.run(['systemctl','stop','aurakingdom'],check=True,timeout=60)
assert not sp.run(['pgrep','-x','ZoneServer'],capture_output=True).stdout
shutil.copy2(drop,backup/drop.name);shutil.copy2(binary,backup/'ZoneServer')
with (backup/'FFDB1.dump').open('wb') as out:
    sp.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
try:
    with binary.open('r+b') as f:
        f.seek(patch['offset']);assert f.read(7)==bytes.fromhex(patch['before'])
        f.seek(patch['offset']);f.write(bytes.fromhex(patch['after']));f.flush();os.fsync(f.fileno())
    shutil.copyfile(source/drop.name,drop)
    assert hashlib.sha256(drop.read_bytes()).hexdigest()==m['drops_after_sha256']
except Exception:
    shutil.copy2(backup/'ZoneServer',binary);shutil.copy2(backup/drop.name,drop)
    sp.run(['systemctl','start','aurakingdom'],check=True,timeout=60)
    raise
sp.run(['systemctl','start','aurakingdom'],check=True,timeout=60)
report=dict(backup=str(backup),gift_entries=len(m['added']),skill_patch=patch,skill_tests=len(m['tests']),
            preserved_pending_links=sql('SELECT json_agg(t) FROM (SELECT elf_id,template_id,link_time FROM elf WHERE player_id=50000001 AND link_time=-1)t'),
            bot_units_stopped=units,gameplay_verified=False)
(backup/'report.json').write_text(json.dumps(report,indent=2))
Path('/root/eidolon-repair-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
