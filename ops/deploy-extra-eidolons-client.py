"""Apply the matching client table additions with local backups."""
from pathlib import Path
import datetime, hashlib, json, shutil, subprocess
ROOT=Path(__file__).resolve().parent.parent
PAYLOAD=ROOT/'staging/eidolon-port/payload'
DB=ROOT/'client/Requiem Aurakingdom/data/db'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((PAYLOAD/'manifest.json').read_text())
entries=[e for e in m['files'] if e.get('side')=='client']
check=subprocess.run(['powershell','-NoProfile','-Command',
    "@(Get-Process Game,game.bin,Launcher -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,check=True)
assert check.stdout.strip()=='0','Close Game.exe and the launcher before applying client tables'
for e in entries:
    assert sha(DB/e['name'])==e['before'],e['name']+' changed since preparation'
    assert sha(PAYLOAD/e['payload'])==e['after']
backup=ROOT/'private/client-original'/('extra-eidolons-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(parents=True)
for e in entries: shutil.copy2(DB/e['name'],backup/e['name'])
try:
    for e in entries:
        shutil.copyfile(PAYLOAD/e['payload'],DB/e['name'])
        assert sha(DB/e['name'])==e['after']
except BaseException:
    for e in entries: shutil.copy2(backup/e['name'],DB/e['name'])
    raise
report=dict(backup=str(backup),files=[e['name'] for e in entries],verified=True)
(backup/'report.json').write_text(json.dumps(report,indent=2))
(ROOT/'docs/extra-eidolons-client-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
