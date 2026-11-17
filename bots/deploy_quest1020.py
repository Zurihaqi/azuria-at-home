"""Deploy native resource classification with bot-only restarts and backups."""
from pathlib import Path
import datetime
import hashlib
import json
import py_compile
import shutil
import subprocess as sp
import sys
import time

root=Path('/opt/ak-bot-prototype')
stage=root/'quest1017-staging'
expected={
    'assist.py':'5b48c1fa594a64f742a140f9af209451706d047d2a5abc70d5be026737a8bf7d',
    'objectives.py':'0e826148822e8eb4de1ec4adf1fbfc033f9cefe7bfce75dbf31f9db061bae05d',
    'probe_login.py':'52d8fe1ee2de4704208a7c94e4ff8dca33ce89a084c4d3bd8be04b268c1f7586',
}
for name,digest in expected.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name+' changed since review'
    py_compile.compile(str(stage/name),doraise=True)
sys.path.insert(0,str(stage))
from assist import resource_templates
resources=sorted(resource_templates('/root/hxsy/Data/db/S_Biology.ini'))
assert all(n in resources for n in (40334,40335,40336,40337))
assert 41165 not in resources and 40323 not in resources
assert sp.run(['systemctl','is-active','--quiet','aurakingdom']).returncode==0
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/ak-bots')/('resource-classification-'+stamp)
backup.mkdir(mode=0o700)
for name in expected:shutil.copy2(root/name,backup/name)
catalog=root/'maps/resource-templates.json'
if catalog.exists():shutil.copy2(catalog,backup/catalog.name)
sp.run(['systemctl','stop','ak-bot-awan','ak-bot-arden'],check=True,timeout=50)
catalog.write_text(json.dumps(resources));catalog.chmod(0o644)
for name in expected:
    shutil.copy2(stage/name,root/name)
    (root/name).chmod(0o644)
print('Resource catalog installed: '+str(len(resources))+' native resource templates.',flush=True)
time.sleep(30)
for profile in ('awan','arden'):
    sp.run(['/usr/bin/python3',str(root/'bot_control.py'),'start',profile],check=True)
    time.sleep(3)
report=dict(backup=str(backup),resources=len(resources),game_restarted=False,database_edits=False,
            files={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in expected})
(backup/'verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
