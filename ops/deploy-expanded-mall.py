from pathlib import Path
import datetime,hashlib,json,os,re,subprocess
from patch_mall_enhancement import patch
os.umask(0o077)
def sql(db,text):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=text,text=True,capture_output=True,cwd='/tmp',check=True)
 return r.stdout.strip()
def hashes():
 names=sql('FFDB1',"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename;").splitlines()
 out={}
 for name in names:
  assert re.fullmatch('[a-z0-9_]+',name)
  data=sql('FFDB1',f'SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,\'[]\') FROM "{name}" t;')
  out[name]=hashlib.sha256(data.encode()).hexdigest()
 return out
assert sql('FFDB1','SELECT quit FROM player_characters WHERE id=50000001 AND account_id=2419;')=='1'
catalog=json.loads(Path('/root/gear-catalog-split.json').read_text())
unlocks=json.loads(Path('/root/unlock-manifest.json').read_text())
assert len(catalog['items'])==10616 and len(catalog['sections'])==43
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('pre-expanded-mall-'+stamp);backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
 for db in ['FFAccount','FFDB1']:
  with (backup/(db+'.dump')).open('wb') as out:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',db],stdout=out,cwd='/tmp',check=True)
 before=hashes();(backup/'quests-before.json').write_text(json.dumps(before,indent=2))
 stock_sql="SELECT md5(string_agg(row_to_json(t)::text,',' ORDER BY item_group,detail_type,item_index,money_unit)) FROM itemmall t WHERE note NOT LIKE 'codex:gear-catalog:%';"
 stock_before=sql('FFAccount',stock_sql)
 patch()
 rows=[]
 for item in catalog['items']:
  assert all(isinstance(item[k],int) for k in ['id','index','detail_type'])
  rows.append(f"({item['id']},6,{item['detail_type']},{item['index']},1,1,1,0,0,0,0,-1,1,0,0,'',0,'codex:gear-catalog:v1')")
 sql('FFAccount',"BEGIN; DELETE FROM itemmall WHERE note LIKE 'codex:gear-catalog:%'; INSERT INTO itemmall(item_id,item_group,detail_type,item_index,item_num,money_unit,point,special_price,num_limit,flags,level_limit,gender,sell,not_sell_date,sell_date,message,beginner_only_time,note) VALUES "+','.join(rows)+'; COMMIT;')
 # Account titles are the authoritative set loaded by MissionServer LoadAppellation.
 titles=','.join(f'(2419,{i})' for i in unlocks['titles'])
 panels=','.join(f'(2419,{i},extract(epoch from now())::int,0,0)' for i in unlocks['panels'])
 # LoadBase computes AccountSplitID as account_id % 10, with remainder zero mapped to 10.
 suffix=2419%10 or 10
 medals=','.join(f"(2419,{m['id']},{m['required']},1,1,extract(epoch from now())::int)" for m in unlocks['medals'])
 sql('FFDB1',f'''BEGIN;
UPDATE player_characters SET skill_point=1000 WHERE id=50000001 AND account_id=2419;
INSERT INTO player_appellation(account_id,appellation_id) SELECT v.account_id,v.appellation_id FROM (VALUES {titles}) AS v(account_id,appellation_id) WHERE NOT EXISTS(SELECT 1 FROM player_appellation p WHERE p.account_id=v.account_id AND p.appellation_id=v.appellation_id);
INSERT INTO account_panel(account_id,panel_id,get_panel_time,due_time,real_duration) VALUES {panels} ON CONFLICT(account_id,panel_id) DO UPDATE SET due_time=0,real_duration=0;
INSERT INTO player_characters_achievement{suffix}(account_id,achievement_id,point,completed_num,completed,completed_time) VALUES {medals} ON CONFLICT(account_id,achievement_id) DO UPDATE SET point=excluded.point,completed_num=1,completed=1,completed_time=excluded.completed_time;
COMMIT;''')
 assert hashes()==before, 'Quest data changed unexpectedly'
 assert sql('FFAccount',stock_sql)==stock_before, 'Original shop stock changed unexpectedly'
 report=dict(backup=str(backup),mall_items=len(catalog['items']),mall_sections=len(catalog['sections']),
 titles=int(sql('FFDB1','SELECT count(DISTINCT appellation_id) FROM player_appellation WHERE account_id=2419;')),
 panels=int(sql('FFDB1','SELECT count(*) FROM account_panel WHERE account_id=2419;')),
 medals=len(unlocks['medals']),medal_table=f'player_characters_achievement{suffix}',envoy_points=1000,
 quest_tables_unchanged=True,original_stock_unchanged=True,fortification='Native upgrade routine, up to +30 on supported types',stars='5 on eligible quality/type equipment',
 validation='Database/hash checks passed; live cache and gameplay validation pending')
 Path('/root/expanded-mall-deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
finally:
 subprocess.run(['systemctl','start','aurakingdom'],check=True)
