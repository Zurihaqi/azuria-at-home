"""Stage the reviewed Guitar conversion and back up/update the closed client."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess as sp
import tarfile

ROOT=Path(__file__).resolve().parent.parent
stage=ROOT/'staging/guitar'
client=ROOT/'client/Requiem Aurakingdom/data/db'
manifest=json.loads((stage/'manifest.json').read_text())
check=sp.run(['powershell','-NoProfile','-Command',
    "@(Get-Process -Name Game,game.bin -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,check=True)
assert check.stdout.strip()=='0','Close the game before client table changes'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=ROOT/'private/client-original'/('guitar-switch-'+stamp)
backup.mkdir()
for entry in manifest['files']:
    if entry['name'] not in ('C_Item.ini','T_Item.ini'):continue
    target=client/entry['name']
    assert hashlib.sha256(target.read_bytes()).hexdigest()==entry['before'],str(target)+' changed'
    assert hashlib.sha256((stage/entry['name']).read_bytes()).hexdigest()==entry['after']
    shutil.copy2(target,backup/entry['name'])
for entry in manifest['files']:
    if entry['name'] in ('C_Item.ini','T_Item.ini'):
        shutil.copy2(stage/entry['name'],client/entry['name'])
(backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
archive=stage/'deployment.tar'
with tarfile.open(archive,'w') as tar:
    for name in ('S_Item.ini','server-T_Item.ini','manifest.json'):
        tar.add(stage/name,arcname=name)
    tar.add(ROOT/'ops/apply-guitar-switch-guest.py',arcname='apply.py')
sp.run(['python',str(ROOT/'ops/vm.py'),'put',str(archive),'/tmp/guitar-switch.tar'],check=True)
print(json.dumps(dict(client_backup=str(backup),client_tables_updated=True,archive_staged=True)))
