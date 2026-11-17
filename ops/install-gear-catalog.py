from pathlib import Path
import datetime,json,os,subprocess
os.umask(0o077)
config=json.loads(Path('/root/gear-catalog.json').read_text())
def sql(db,text):
    result=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=text,text=True,capture_output=True,cwd='/tmp')
    if result.returncode:raise RuntimeError(result.stderr)
    return result.stdout.strip()
if sql('FFDB1','SELECT count(*) FROM player_characters WHERE quit=0;')!='0':
    raise RuntimeError('Players must be offline for this deployment')
group=config['item_group'];marker=config['marker']
assert group==6 and marker=='codex:gear-catalog:v1'
if sql('FFAccount',f"SELECT count(*) FROM itemmall WHERE item_group={group} AND note <> '{marker}';")!='0':
    raise RuntimeError('Category is no longer empty; refusing replacement')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('pre-gear-shop-'+stamp)
backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
    for database in ['FFAccount','FFDB1']:
        with (backup/(database+'.dump')).open('wb') as out:
            subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',database],stdout=out,check=True,cwd='/tmp')
    before=sql('FFAccount',f"SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,'[]') FROM itemmall t WHERE note <> '{marker}';")
    rows=[]
    for row in config['items']:
        assert all(isinstance(row[k],int) for k in ['id','index','detail_type'])
        rows.append(f"({row['id']},6,{row['detail_type']},{row['index']},1,1,1,0,0,0,0,-1,1,0,0,'',0,'{marker}')")
    statement=f"BEGIN; DELETE FROM itemmall WHERE note='{marker}'; INSERT INTO itemmall(item_id,item_group,detail_type,item_index,item_num,money_unit,point,special_price,num_limit,flags,level_limit,gender,sell,not_sell_date,sell_date,message,beginner_only_time,note) VALUES "+','.join(rows)+'; COMMIT;'
    sql('FFAccount',statement)
    after=sql('FFAccount',f"SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,'[]') FROM itemmall t WHERE note <> '{marker}';")
    if before!=after:raise RuntimeError('Existing shop stock changed unexpectedly')
    report={'items':len(rows),'sections':config['counts'],'price':'1 AP each','existing_stock_unchanged':True,'category':6,'backup':str(backup),'validation':'Database installed; in-game display and purchase pending'}
    Path('/root/gear-shop-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
finally:
    subprocess.run(['systemctl','start','aurakingdom'],check=True)
