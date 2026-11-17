from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess
os.umask(0o077)
def sql(db,q):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=q,text=True,capture_output=True,cwd='/tmp')
 if r.returncode:raise RuntimeError(r.stderr)
 return r.stdout.strip()
manifest=json.loads(Path('/root/sovereign-v2-final-manifest.json').read_text())
assert sql('FFDB1','SELECT count(*) FROM player_characters WHERE quit=0')=='0'
for e in manifest['server']:
 assert hashlib.sha256((Path('/root/hxsy/Data/db')/e['name']).read_bytes()).hexdigest()==e['before'],e['name']
backup=Path('/var/backups/aurakingdom')/('pre-sovereign-v2-final-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True);changes=[]
try:
 with (backup/'FFDB1.dump').open('wb') as out:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
 ids=','.join(map(str,manifest['unused_title_ids']))
 removed=sql('FFDB1',f"SELECT coalesce(json_agg(t),'[]') FROM (SELECT * FROM player_appellation WHERE account_id=2419 AND appellation_id IN ({ids})) t")
 (backup/'unused-title-unlocks.json').write_text(removed)
 for e in manifest['server']:
  target=Path('/root/hxsy/Data/db')/e['name'];saved=backup/e['name'];shutil.copy2(target,saved);changes.append((target,saved))
  payload=(Path('/root/sovereign-v2-final')/e.get('payload',e['name'])).read_bytes();assert hashlib.sha256(payload).hexdigest()==e['after'];target.write_bytes(payload)
 sql('FFDB1',f'DELETE FROM player_appellation WHERE account_id=2419 AND appellation_id IN ({ids});')
 report={'backup':str(backup),'unused_title_unlocks_removed':len(json.loads(removed)),'server_text_records_repaired':manifest['server_text'],'independent_passives':10,'armor_piercing_corrected':True}
 Path('/root/sovereign-v2-final-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
except Exception:
 for target,saved in changes:shutil.copy2(saved,target)
 raise
finally:subprocess.run(['systemctl','start','aurakingdom'],check=True)
