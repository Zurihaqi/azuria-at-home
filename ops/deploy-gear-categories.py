"""Guest deployment: shop categories and bounded offline character boosts."""
from pathlib import Path
import datetime,hashlib,json,os,re,subprocess
os.umask(0o077)

def sql(db,text):
    result=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=text,text=True,capture_output=True,cwd='/tmp',check=True)
    return result.stdout.strip()

def quests():
    names=sql('FFDB1',"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename;").splitlines()
    result={}
    for name in names:
        assert re.fullmatch('[a-z0-9_]+',name)
        data=sql('FFDB1',f'SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,\'[]\') FROM "{name}" t;')
        result[name]=hashlib.sha256(data.encode()).hexdigest()
    return result

current=json.loads(sql('FFDB1','SELECT row_to_json(t) FROM player_characters t WHERE id=50000001;'))
assert current['given_name']=='Zrymund' and current['account_id']==2419 and current['quit']==1
config=json.loads(Path('/root/gear-catalog-split.json').read_text())
assert len(config['items'])==3630 and len(config['sections'])==40
assert sql('FFAccount',"SELECT count(*) FROM itemmall WHERE item_group=6 AND note NOT LIKE 'codex:gear-catalog:%';")=='0'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('pre-gear-categories-'+stamp)
backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
    for db in ['FFAccount','FFDB1']:
        with (backup/(db+'.dump')).open('wb') as out:
            subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',db],cwd='/tmp',stdout=out,check=True)
    before=quests()
    (backup/'quests-before.json').write_text(json.dumps(before,indent=2))
    stock_before=sql('FFAccount',"SELECT md5(string_agg(row_to_json(t)::text,',' ORDER BY item_group,detail_type,item_index,money_unit)) FROM itemmall t WHERE note NOT LIKE 'codex:gear-catalog:%';")
    values=[]
    for item in config['items']:
        assert all(isinstance(item[k],int) for k in ['id','index','detail_type'])
        values.append(f"({item['id']},6,{item['detail_type']},{item['index']},1,1,1,0,0,0,0,-1,1,0,0,'',0,'codex:gear-catalog:v1')")
    sql('FFAccount',"BEGIN; DELETE FROM itemmall WHERE note LIKE 'codex:gear-catalog:%'; INSERT INTO itemmall(item_id,item_group,detail_type,item_index,item_num,money_unit,point,special_price,num_limit,flags,level_limit,gender,sell,not_sell_date,sell_date,message,beginner_only_time,note) VALUES "+','.join(values)+'; COMMIT;')
    sql('FFDB1','''BEGIN;
UPDATE player_potential_point SET atk=1000,def=1000 WHERE player_id=50000001;
INSERT INTO player_weapon_expert(player_id,type,level,exp) VALUES(50000001,0,70,0),(50000001,1,70,0)
ON CONFLICT(player_id,type) DO UPDATE SET level=70,exp=0;
COMMIT;''')
    after=quests()
    stock_after=sql('FFAccount',"SELECT md5(string_agg(row_to_json(t)::text,',' ORDER BY item_group,detail_type,item_index,money_unit)) FROM itemmall t WHERE note NOT LIKE 'codex:gear-catalog:%';")
    assert before==after, 'Unexpected quest-table change'
    assert stock_before==stock_after, 'Unexpected original-stock change'
    report=dict(backup=str(backup),items=3630,sections=40,point=1,special_price=0,
                original_shop_stock_unchanged=True,quest_tables_unchanged=True,
                character='Zrymund',level=current['level'],spare_attack_points=1000,spare_defense_points=1000,
                weapon_mastery_levels={'0':70,'1':70},mastery_cap_source='Live CFormula AllFormulaParas +0x8d8 = 70; SetWeaponExpertLevel accepts types 0 and 1',
                validation='Database values and quest/original stock hashes verified; runtime/client validation pending')
    Path('/root/gear-categories-deployment.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
finally:
    subprocess.run(['systemctl','start','aurakingdom'],check=True)
