"""Back up and enable free native fitting-room purchases, preserving guards."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import shutil
import subprocess as sp

os.umask(0o077)
root=Path('/opt/ak-bot-prototype')
stage=root/'quest1017-staging'
manifest=json.loads(Path('/tmp/free-preview-patch.json').read_text())
binary=Path('/root/hxsy/ZoneServer/ZoneServer')

def sql(db,q):
    r=sp.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=q,text=True,capture_output=True,cwd='/tmp')
    if r.returncode:raise RuntimeError(r.stderr)
    return r.stdout.strip()

assert sql('FFDB1','SELECT count(*) FROM player_characters WHERE quit=0 AND id NOT IN (50000002,50000003)')=='0','Human players must log out before restarting the game'
expected={'probe_login.py':'304981ae00a7e85223788306fdf9f44c4655505e5765c56f0b8d207a9a5951fb',
          'quest_engine.py':'e879faeb864ebc133236bc942eb25dfd228fbf42d71a37c885a9abb661015d4e'}
for name,digest in expected.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name+' changed since review'
with binary.open('rb') as f:
    for patch in manifest['patches']:
        f.seek(patch['offset']);assert f.read(len(bytes.fromhex(patch['before'])))==bytes.fromhex(patch['before'])
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('free-preview-'+stamp)
backup.mkdir(mode=0o700)
units=[u for u in ('ak-bot-awan','ak-bot-arden') if sp.run(['systemctl','show',u,'-p','LoadState','--value'],text=True,capture_output=True).stdout.strip()=='loaded']
if units:sp.run(['systemctl','stop',*units],check=True,timeout=60)
sp.run(['systemctl','stop','aurakingdom'],check=True,timeout=60)
success=False
try:
    assert sql('FFDB1','SELECT count(*) FROM player_characters WHERE quit=0 AND id NOT IN (50000002,50000003)')=='0'
    with (backup/'FFAccount.dump').open('wb') as out:
        sp.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFAccount'],stdout=out,cwd='/tmp',check=True)
    before=sql('FFAccount',"SELECT coalesce(json_agg(t ORDER BY item_id),'[]') FROM dressroom t")
    (backup/'dressroom-before.json').write_text(before)
    shutil.copy2(binary,backup/'ZoneServer')
    before_hash=hashlib.sha256(binary.read_bytes()).hexdigest()
    with binary.open('r+b') as f:
        for patch in manifest['patches']:
            f.seek(patch['offset']);f.write(bytes.fromhex(patch['after']))
        f.flush();os.fsync(f.fileno())
    # Deliver the actual previewed item directly, including previously disabled
    # preview-only entries. Model, category, ordering and dye data are preserved.
    sql('FFAccount','BEGIN; UPDATE dressroom SET price=0,fortune_item_id=item_id; COMMIT;')
    assert sql('FFAccount','SELECT count(*) FROM dressroom WHERE price<>0 OR fortune_item_id<>item_id')=='0'
    for name in (*expected,'crafting.py'):
        if (root/name).exists():shutil.copy2(root/name,backup/name)
        shutil.copy2(stage/name,root/name);(root/name).chmod(0o644)
    report=dict(backup=str(backup),entries=int(sql('FFAccount','SELECT count(*) FROM dressroom')),
        zero_prices=True,direct_delivery=True,emulation_tests=manifest['tests_passed'],
        binary_before=before_hash,binary_after=hashlib.sha256(binary.read_bytes()).hexdigest(),
        crafting_driver='Native recipe-chain pilot enabled for quest 2092',gameplay_purchase_verified=False)
    (backup/'report.json').write_text(json.dumps(report,indent=2));Path('/root/free-preview-report.json').write_text(json.dumps(report,indent=2))
    success=True
    print(json.dumps(report),flush=True)
finally:
    if success:sp.run(['systemctl','start','aurakingdom'],check=True,timeout=60)
    else:print('Deployment interrupted; game kept stopped. Backup: '+str(backup),flush=True)
