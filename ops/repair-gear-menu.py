from pathlib import Path
import json,subprocess
def sql(text):
    r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFAccount'],input=text,text=True,capture_output=True,cwd='/tmp')
    if r.returncode:raise RuntimeError(r.stderr)
    return r.stdout.strip()
config=json.loads(Path('/root/gear-catalog.json').read_text())
marker='codex:gear-catalog:v1'
if sql("SELECT count(*) FROM itemmall WHERE item_group=5 AND detail_type=2 AND note <> 'codex:gear-catalog:v1';")!='0':
    raise RuntimeError('Target submenu is occupied')
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
    rows=[]
    for index,item in enumerate(config['items'],1001):
        rows.append(f"({item['id']},5,2,{index},1,1,1,0,0,0,0,-1,1,0,0,'',0,'{marker}')")
    # Known working mall-template control distinguishes menu filtering from item lookup.
    index=1001+len(rows)
    rows.append(f"(40003,5,2,{index},1,1,1,0,0,0,0,-1,1,0,0,'Catalog loading check',0,'codex:gear-catalog:probe')")
    sql("BEGIN; DELETE FROM itemmall WHERE note IN ('codex:gear-catalog:v1','codex:gear-catalog:probe'); INSERT INTO itemmall(item_id,item_group,detail_type,item_index,item_num,money_unit,point,special_price,num_limit,flags,level_limit,gender,sell,not_sell_date,sell_date,message,beginner_only_time,note) VALUES "+','.join(rows)+'; COMMIT;')
    print('Installed gear submenu in Gear Improvement, with one known-good mall control item')
finally:
    subprocess.run(['systemctl','start','aurakingdom'],check=True)
