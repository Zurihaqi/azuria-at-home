from pathlib import Path
import datetime,hashlib,json,os,re,shutil,struct,subprocess
os.umask(0o077)
def sql(db,q):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=q,text=True,capture_output=True,cwd='/tmp',check=True)
 return r.stdout.strip()
def quests():
 names=sql('FFDB1',"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename;").splitlines();out={}
 for n in names:
  assert re.fullmatch('[a-z0-9_]+',n)
  data=sql('FFDB1',f'SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,\'[]\') FROM "{n}" t;')
  out[n]=hashlib.sha256(data.encode()).hexdigest()
 return out
assert sql('FFDB1','SELECT quit FROM player_characters WHERE id=50000001 AND account_id=2419;')=='1'
manifest=json.loads(Path('/root/zrymund-set.json').read_text())
catalog=json.loads(Path('/root/gear-catalog-split.json').read_text())
assert len(catalog['items'])==10627 and len(catalog['sections'])==44
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('pre-custom-set-'+stamp);backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
 for db in ['FFAccount','FFDB1']:
  with (backup/(db+'.dump')).open('wb') as out:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',db],stdout=out,cwd='/tmp',check=True)
 before=quests();gold=sql('FFDB1','SELECT gold,bind_gold FROM player_characters WHERE id=50000001;')
 for name,fragment,key in [('S_Item.ini','items.ini','items'),('S_Enchant.ini','enchants.ini','enchant_ids')]:
  target=Path('/root/hxsy/Data/db')/name;original=target.read_bytes()
  ids=[i['id'] for i in manifest['items']] if key=='items' else manifest[key]
  for i in ids:
   assert not re.search(rb'(?m)^'+str(i).encode()+rb'\|',original),(name,i)
  shutil.copy2(target,backup/name)
  target.write_bytes(original.rstrip(b'\r\n')+b'\r\n'+(Path('/root/custom-set')/fragment).read_bytes())
 binary=Path('/root/hxsy/ZoneServer/ZoneServer')
 with binary.open('r+b') as f:
  hdr=f.read(64);vals=struct.unpack('<16sHHIQQQIHHHHHH',hdr)
  f.seek(vals[5]);ph=f.read(vals[9]*vals[10]);table=None
  for j in range(vals[10]):
   seg=struct.unpack_from('<IIQQQQQQ',ph,j*vals[9])
   if seg[0]==1 and seg[3]<=0x16bb000<seg[3]+seg[5]:table=seg[2]+0x16bb000-seg[3]
  assert table is not None
  changes=[]
  for item in manifest['items']:
   typ=item['type'];flags=(1 if typ in set(range(1,6))|set(range(7,25))|{37,38} else 0)|(2 if 1<=typ<=24 else 0)
   f.seek(table+item['id']);old=f.read(1);assert old==b'\0'
   changes.append({'offset':table+item['id'],'before':old.hex(),'after':flags})
  (backup/'enhancement-mask-before.json').write_text(json.dumps(changes,indent=2))
  for change in changes:f.seek(change['offset']);f.write(bytes([change['after']]))
 rows=[]
 for item in catalog['items']:
  assert all(isinstance(item[k],int) for k in ['id','index','detail_type'])
  rows.append(f"({item['id']},6,{item['detail_type']},{item['index']},1,1,1,0,0,0,0,-1,1,0,0,'',0,'codex:gear-catalog:v1')")
 sql('FFAccount',"BEGIN; DELETE FROM itemmall WHERE note LIKE 'codex:gear-catalog:%'; INSERT INTO itemmall(item_id,item_group,detail_type,item_index,item_num,money_unit,point,special_price,num_limit,flags,level_limit,gender,sell,not_sell_date,sell_date,message,beginner_only_time,note) VALUES "+','.join(rows)+'; COMMIT;')
 assert before==quests()
 assert gold==sql('FFDB1','SELECT gold,bind_gold FROM player_characters WHERE id=50000001;')
 report={'set':manifest['name'],'backup':str(backup),'item_ids':[x['id'] for x in manifest['items']],'enchant_ids':manifest['enchant_ids'],'mall_sections':44,'mall_items':10627,'quest_hashes_unchanged':True,'gold_unchanged':True,'delivery':'Item Mall -> AP -> Gear Catalog -> Zrymund Sovereign Set, 1 AP each','validation':'Definitions deployed, server loader and gameplay checks pending'}
 Path('/root/zrymund-set-deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
finally:
 subprocess.run(['systemctl','start','aurakingdom'],check=True)
