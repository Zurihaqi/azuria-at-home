"""Install the first verified-warning evasion driver; restart only activity bots."""
from pathlib import Path
import datetime
import hashlib
import json
import py_compile
import shutil
import subprocess as sp
import time

root = Path('/opt/ak-bot-prototype')
stage = root / 'quest1017-staging'
expected = {
    'probe_login.py': '5c2d1fb5613e4a98cafd66ca118fd731a5deae19eb2911759b3f62c2c1f4a701',
    'combat.py': '3cecf3824817249a174966093584b3fa30aa4fc54e6a832e955a1451bc7c8e38',
}
files = (*expected, 'evasion.py')
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name + ' changed since review'
assert not (root / 'evasion.py').exists(), 'Evasion module already exists; review it before replacing'
for name in files:
    py_compile.compile(str(stage / name), doraise=True)
assert sp.run(['systemctl', 'is-active', '--quiet', 'aurakingdom']).returncode == 0
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = Path('/var/backups/ak-bots') / ('evasion-' + stamp)
backup.mkdir(mode=0o700)
for name in expected:
    shutil.copy2(root / name, backup / name)
sp.run(['systemctl', 'stop', 'ak-bot-awan', 'ak-bot-arden'], check=True, timeout=50)
for name in files:
    shutil.copy2(stage / name, root / name)
    (root / name).chmod(0o644)
print('Evasion files installed; waiting for native logout cleanup.', flush=True)
time.sleep(30)
for profile in ('awan', 'arden'):
    sp.run(['/usr/bin/python3', str(root / 'bot_control.py'), 'start', profile], check=True)
    time.sleep(3)
report = dict(backup=str(backup), game_restarted=False, database_edits=False,
              native_combat_avoidance_verified=False,
              replay_verified_spell=58100,
              files={n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in files})
(backup / 'verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
