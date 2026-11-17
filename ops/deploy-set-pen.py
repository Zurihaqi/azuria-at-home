"""Guest-only deployment. No character, quest, inventory or mall database edits."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,subprocess
os.umask(0o077)
manifest=json.loads(Path('/root/set-pen-manifest.json').read_text())

def sql(q):
 return subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp',check=True).stdout.strip()
def snapshots():
 out={}
 for table in ['player_characters','equipment1','equipment2','inventory1','inventory2','final_mission_state1','final_mission_state2','personal_mission_states','mission_trace','player_mission_complete_num','player_spells','player_used_upanisad']:
  text=sql(f'SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,\'[]\') FROM {table} t;')
  out[table]=hashlib.sha256(text.encode()).hexdigest()
 return out
assert sql('SELECT count(*) FROM player_characters WHERE quit=0;')=='0','Everyone must be offline'
server_files=[x for x in manifest['files'] if x['name'].startswith('S_')]
for entry in server_files:
 path=Path('/root/hxsy/Data/db')/entry['name'];payload=Path('/root/pen-upgrade')/entry['name']
 assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['before_sha256'],'Server definition changed since preparation'
 assert hashlib.sha256(payload.read_bytes()).hexdigest()==entry['after_sha256']
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('pre-set-pen-'+stamp);backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
 assert sql('SELECT count(*) FROM player_characters WHERE quit=0;')=='0'
 before=snapshots()
 with (backup/'FFDB1.dump').open('wb') as output:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=output,cwd='/tmp',check=True)
 for entry in server_files:shutil.copy2(Path('/root/hxsy/Data/db')/entry['name'],backup/entry['name'])
 try:
  for entry in server_files:
   path=Path('/root/hxsy/Data/db')/entry['name'];path.write_bytes((Path('/root/pen-upgrade')/entry['name']).read_bytes())
  assert snapshots()==before,'Unexpected game database change'
 except Exception:
  for entry in server_files:shutil.copy2(backup/entry['name'],Path('/root/hxsy/Data/db')/entry['name'])
  raise
 report=dict(backup=str(backup),whip_pen=999,other_piece_pen=100,full_set_pen=1999,new_enchant=180003,
             database_hashes_unchanged=True,validation='Definition deployment complete; native effect load and equipped PEN check pending')
 Path('/root/set-pen-deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
finally:subprocess.run(['systemctl','start','aurakingdom'],check=True)
