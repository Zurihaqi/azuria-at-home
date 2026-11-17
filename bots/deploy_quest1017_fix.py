"""Apply the reviewed quest-1017 combat/stat fix, restarting only the two bots."""
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
    'probe_login.py': '7ca82365df66927f21fc56ed53e6b8e8a41a1096caa0b01ffd70931a5337bca1',
    'potential.py': '8c86191427e02f5084871c08583f6564ae1b0e5a627a4f447a2682bedbd2e34b',
    'battle.py': 'c80f7488cfcb779c583945144d00fe96fc862bbeb262e51f1eee2d0cffefe79b',
    'combat.py': '4ab2125637a64898380dad641f6272115b120c743f6746dcd9751d58dffd6511',
    'objectives.py': 'af0d69e4cda00dff31c7f147a43c82e0c4d8ac68d0948eb3a1c683b5ace43114',
    'quest_engine.py': 'b3329964237d89e2b79a3e375ba067b21edc8b668452409dd39e81b341209063',
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name + ' changed since review'
    py_compile.compile(str(stage / name), doraise=True)
assert sp.run(['systemctl', 'is-active', '--quiet', 'aurakingdom']).returncode == 0
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = Path('/var/backups/ak-bots') / ('quest1017-' + stamp)
backup.mkdir(mode=0o700)
for name in expected:
    shutil.copy2(root / name, backup / name)
sp.run(['systemctl', 'stop', 'ak-bot-awan', 'ak-bot-arden'], check=True, timeout=50)
for name in expected:
    shutil.copy2(stage / name, root / name)
    (root / name).chmod(0o644)
print('Bot files installed; allowing native session cleanup.', flush=True)
time.sleep(30)
for profile in ('awan', 'arden'):
    sp.run(['/usr/bin/python3', str(root / 'bot_control.py'), 'start', profile], check=True)
    time.sleep(3)
report = dict(backup=str(backup), game_restarted=False, database_edits=False,
              files={n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in expected})
(backup / 'verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
