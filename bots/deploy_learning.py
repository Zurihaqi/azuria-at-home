"""Root-only, backed-up bot-code deployment; never restarts game services."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import py_compile
import re
import shutil
import subprocess
import sys

assert os.geteuid() == 0
for unit in ('ak-bot-awan','ak-bot-arden','ak-bot-lab'):
    assert subprocess.run(['systemctl','is-active','--quiet',unit]).returncode != 0, unit + ' must be stopped'
assert subprocess.run(['systemctl','is-active','--quiet','aurakingdom']).returncode == 0
root = Path('/opt/ak-bot-prototype')
stage = root / 'ml-staging'
files = ('encounter_learning.py','combat.py','probe_login.py','item_stream.py')
for name in files:
    py_compile.compile(str(stage/name), doraise=True)
sys.path.insert(0,str(stage))
from encounter_learning import ENEMIES
table = Path('/root/hxsy/Data/db/S_Biology.ini').read_bytes().decode('cp950',errors='surrogateescape')
rows = {int(row[0]):row for block in re.split(r'(?m)(?=^\d+\|)',table)[1:]
        if len(row := block.rstrip().split('|')) > 20}
for ident, level in ENEMIES.items():
    assert int(rows[ident][8]) == level and rows[ident][6] == '2', 'Live biology catalog mismatch'
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = Path('/var/backups/ak-bots') / ('encounter-learning-' + stamp)
backup.mkdir(parents=True, mode=0o700)
backup.chmod(0o700)
manifest = {}
for name in files:
    destination = root/name
    if destination.exists():
        shutil.copy2(destination,backup/name)
    shutil.copy2(stage/name,destination)
    destination.chmod(0o644)
    manifest[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
(backup/'deployment.json').write_text(json.dumps(dict(files=manifest,game_restarted=False),indent=2))
print(json.dumps(dict(backup=str(backup), files=list(files), game_restarted=False,
                     policy='Collection/shadow only; learned selection requires a separate flag')))
