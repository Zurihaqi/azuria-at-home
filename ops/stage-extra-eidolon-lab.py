from pathlib import Path
import hashlib,json,shutil,subprocess as sp,tarfile
def sql(q):
 r=sp.run(['runuser','-u','postgres','--','psql','-X','-tA','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp',check=True);return r.stdout.strip()
assert sql('SELECT count(*) FROM player_characters WHERE quit=0 AND id NOT IN (50000002,50000003)')=='0','A human is online'
assert sp.run(['systemctl','is-active','--quiet','ak-bot-lab']).returncode!=0
stage=Path('/tmp/extra-eidolon-port');stage.mkdir(exist_ok=True)
with tarfile.open('/tmp/extra-eidolon-payload.tgz') as archive:
 for entry in archive:
  assert entry.isfile() and Path(entry.name).name==entry.name
  (stage/entry.name).write_bytes(archive.extractfile(entry).read())
m=json.loads((stage/'manifest.json').read_text())
for entry in m['files']:
 if entry.get('side')=='client':continue
 p=Path('/root/hxsy/Data/db')/entry['name'];assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['before'],entry['name']
root=Path('/var/lib/ak-bot-lab/game');assert root.resolve()==root and (root/'.ak-bot-lab').is_file()
for unit in ('ak-bot-awan','ak-bot-arden'):
 if sp.run(['systemctl','is-active','--quiet',unit]).returncode==0:sp.run(['systemctl','stop',unit],check=True,timeout=60)
sp.run(['systemctl','stop','aurakingdom'],check=True,timeout=60)
assert sp.run(['pgrep','-x','ZoneServer'],capture_output=True).returncode==1
shutil.copytree('/root/hxsy/Data/db',root/'Data/db',dirs_exist_ok=True)
for server in ('TicketServer','GatewayServer','LoginServer','MissionServer','WorldServer','ZoneServer'):
 shutil.copy2(Path('/root/hxsy')/server/server,root/server/server)
for entry in m['files']:
 if entry.get('side')=='client':continue
 p=stage/entry.get('payload',entry['name']);assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['after']
 shutil.copyfile(p,root/'Data/db'/entry['name'])
Path('/var/lib/ak-bot-lab/run/extra-eidolon-manifest.json').write_text(json.dumps(m))
Path('/var/lib/ak-bot-lab/run/extra-eidolon-stage.json').write_text(json.dumps(dict(counts=m['counts'],state='staged')))
sp.run(['python3','/root/ak-bot-explore/lab.py','start-full'],check=True,timeout=60)
print('Port staged only in the isolated lab. Production data and databases unchanged.')
