from pathlib import Path
import datetime,hashlib,json,os,re,shutil,subprocess
os.umask(0o077)
def sql(q):
 result=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp')
 if result.returncode:raise RuntimeError(result.stderr)
 return result.stdout.strip()
def digest(q):return hashlib.sha256(sql(q).encode()).hexdigest()
def questhashes():
 out={}
 for n in sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename").splitlines():
  assert re.fullmatch('[a-z0-9_]+',n)
  out[n]=digest(f"SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,'[]') FROM {n} t")
 return out
if os.environ.get('INSPECT_ONLY'):
 print(json.dumps({'character':sql('SELECT id,level,quit FROM player_characters WHERE id=50000001'),
 'config_levels':{p.name:re.findall(r'(?im)^MAXLevel\s*=\s*\d+',p.read_text(errors='replace')) for p in Path('/root/hxsy').glob('config*.ini')},
 'columns':{t:sql(f"SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='{t}'") for t in ['equipment1','inventory1']}}));raise SystemExit
manifest=json.loads(Path('/root/sovereign-v2-manifest.json').read_text())
assert sql('SELECT count(*) FROM player_characters WHERE quit=0')=='0','Players must be offline'
entries=[e for e in manifest['files'] if e['name'].startswith('S_')]
for e in entries:
 assert hashlib.sha256((Path('/root/hxsy/Data/db')/e['name']).read_bytes()).hexdigest()==e['before_sha256'],e['name']
 assert hashlib.sha256((Path('/root/sovereign-v2')/e['name']).read_bytes()).hexdigest()==e['after_sha256']
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('pre-sovereign-v2-'+stamp);backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
changes=[]
try:
 assert sql('SELECT count(*) FROM player_characters WHERE quit=0')=='0'
 with (backup/'FFDB1.dump').open('wb') as out:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
 before=questhashes();gold=sql('SELECT gold,bind_gold,level,exp FROM player_characters WHERE id=50000001')
 for e in entries:
  target=Path('/root/hxsy/Data/db')/e['name'];saved=backup/e['name'];shutil.copy2(target,saved);changes.append((target,saved))
  target.write_bytes((Path('/root/sovereign-v2')/e['name']).read_bytes())
 for target in Path('/root/hxsy').glob('config*.ini'):
  raw=target.read_bytes();patched,n=re.subn(rb'(?im)^(MAXLevel\s*=\s*)\d+',lambda m:m[1]+b'150',raw)
  if not n:continue
  saved=backup/target.name;shutil.copy2(target,saved);changes.append((target,saved));target.write_bytes(patched)
 # Move complete item instances without changing their attributes or identifiers.
 columns={t:sql(f"SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='{t}'") for t in ['equipment1','inventory1']}
 assert columns['equipment1']==columns['inventory1'],'Inventory schemas differ'
 cols=columns['inventory1'].split(',')
 equipped=json.loads(sql("SELECT coalesce(json_agg(t),'[]') FROM (SELECT id,item_id FROM equipment1 WHERE player_id=50000001 AND item_id BETWEEN 61586 AND 61596 AND (SELECT level FROM player_characters WHERE id=50000001)<130 ORDER BY loc) t"))
 free=[i for i in range(20) if str(i) not in sql('SELECT loc FROM inventory1 WHERE player_id=50000001 AND container_index=8').splitlines()]
 assert len(free)>=len(equipped)
 statements=['BEGIN;']
 for item,slot in zip(equipped,free):
  values=','.join('8' if c=='container_index' else str(slot) if c=='loc' else c for c in cols)
  statements.append(f"INSERT INTO inventory1 ({','.join(cols)}) SELECT {values} FROM equipment1 WHERE id={item['id']} AND player_id=50000001; DELETE FROM equipment1 WHERE id={item['id']} AND player_id=50000001;")
 # Repair negative free-point balances by refunding existing allocations.
 statements.append('UPDATE player_potential_point SET atk=atk+point1+point2+point3,def=def+point4+point5+point6,point1=0,point2=0,point3=0,point4=0,point5=0,point6=0 WHERE player_id=50000001 AND (atk<0 OR def<0);')
 statements.append('COMMIT;');sql('\n'.join(statements))
 assert questhashes()==before,'Quest data changed'
 assert gold==sql('SELECT gold,bind_gold,level,exp FROM player_characters WHERE id=50000001')
 report={'backup':str(backup),'cap_internal':150,'gear_requirement_internal':130,'moved_to_bag_8':equipped,'quest_hashes_unchanged':True,'level_exp_currency_unchanged':True,'points':sql('SELECT atk,def FROM player_potential_point WHERE player_id=50000001'),'server_files':[str(p) for p,s in changes]}
 (backup/'report.json').write_text(json.dumps(report,indent=2));Path('/root/sovereign-v2-deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
except Exception:
 for target,saved in changes:shutil.copy2(saved,target)
 raise
finally:subprocess.run(['systemctl','start','aurakingdom'],check=True)
