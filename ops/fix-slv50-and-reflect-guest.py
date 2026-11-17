from pathlib import Path
import datetime,hashlib,json,os,re,shutil,subprocess
os.umask(0o077)
def sql(q):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp')
 if r.returncode:raise RuntimeError(r.stderr)
 return r.stdout.strip()
def hashes():
 out={}
 tables=sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename").splitlines()
 tables+=['equipment1','equipment2','inventory1','inventory2','player_potential_point','player_spells','player_used_upanisad']
 for name in tables:
  assert re.fullmatch('[a-z0-9_]+',name)
  value=sql(f"SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,'[]') FROM {name} t")
  out[name]=hashlib.sha256(value.encode()).hexdigest()
 return out
manifest=json.loads(Path('/root/slv50-reflect-manifest.json').read_text())
assert sql('SELECT count(*) FROM player_characters WHERE quit=0')=='0','Everyone must be offline'
assert sql('SELECT level FROM player_characters WHERE id=50000001')=='150'
entries=[e for e in manifest['files'] if e['name'].startswith('S_')]
for e in entries:assert hashlib.sha256((Path('/root/hxsy/Data/db')/e['name']).read_bytes()).hexdigest()==e['before']
backup=Path('/var/backups/aurakingdom')/('pre-slv50-reflect-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True);changes=[]
try:
 assert sql('SELECT count(*) FROM player_characters WHERE quit=0')=='0'
 with (backup/'FFDB1.dump').open('wb') as out:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
 before=hashes();character=sql("SELECT row_to_json(t) FROM (SELECT * FROM player_characters WHERE id=50000001) t");(backup/'character.json').write_text(character)
 for e in entries:
  target=Path('/root/hxsy/Data/db')/e['name'];saved=backup/e['name'];shutil.copy2(target,saved);changes.append((target,saved))
  raw=(Path('/root/slv50-reflect')/e['name']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['after'];target.write_bytes(raw)
 sql('UPDATE player_characters SET level=149 WHERE id=50000001 AND quit=1 AND level=150;')
 after=json.loads(sql("SELECT row_to_json(t) FROM (SELECT * FROM player_characters WHERE id=50000001) t"));expected=json.loads(character);expected['level']=149;assert after==expected
 assert hashes()==before,'Unexpected quest, inventory, gear or point change'
 report={'backup':str(backup),'character_level':149,'exp':after['exp'],'cap':150,'reference_row':151,'reflection_percent':100,'quests_inventory_equipment_points_unchanged':True,'currency_unchanged':True}
 Path('/root/slv50-reflect-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
except Exception:
 for target,saved in changes:shutil.copy2(saved,target)
 raise
finally:subprocess.run(['systemctl','start','aurakingdom'],check=True)
