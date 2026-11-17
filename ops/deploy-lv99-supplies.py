"""Explicitly requested quest skip, bounded EXP and compatible stock mall supplies."""
from pathlib import Path
import collections,datetime,hashlib,json,os,subprocess
os.umask(0o077)
data=json.loads(Path('/root/lv99-supplies-manifest.json').read_text())
CHAR=50000001

def sql(db,text):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=text,text=True,capture_output=True,cwd='/tmp',check=True)
 return r.stdout.strip()
def rows(db,query):return json.loads(sql(db,"SELECT coalesce(json_agg(t),'[]') FROM ("+query+') t;'))
def digest(db,query):return hashlib.sha256(json.dumps(rows(db,query),sort_keys=True).encode()).hexdigest()

before=rows('FFDB1',f'SELECT * FROM player_characters WHERE id={CHAR}')[0]
assert before['given_name']=='Zrymund' and before['account_id']==2419 and before['quit']==1
assert sql('FFDB1','SELECT count(*) FROM player_characters WHERE quit=0;')=='0','Everyone must be offline'
assert before['level']==99 and before['state_flags']&16==0,'Expected a non-awakened level-99 character'
assert hashlib.sha256(Path('/root/hxsy/Data/db/S_Mission.ini').read_bytes()).hexdigest()==data['quest_source_sha256']
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('pre-lv99-supplies-'+stamp);backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
 assert sql('FFDB1','SELECT count(*) FROM player_characters WHERE quit=0;')=='0'
 for db in ['FFDB1','FFAccount']:
  with (backup/(db+'.dump')).open('wb') as output:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',db],stdout=output,cwd='/tmp',check=True)
 (backup/'character-before.json').write_text(json.dumps(before,indent=2))
 inventory={table:digest('FFDB1',f'SELECT * FROM {table} WHERE player_id={CHAR} ORDER BY id') for table in ['inventory1','inventory2','equipment1','equipment2']}
 old_fms=rows('FFDB1',f'SELECT index,state FROM final_mission_state1 WHERE player_id={CHAR} ORDER BY index')
 (backup/'fms-before.json').write_text(json.dumps(old_fms,indent=2))
 packed={r['index']:r['state'] for r in old_fms};wanted={q['id']:1 for q in data['quests']};wanted[2523]=3
 old_states={ident:(packed.get((ident-1)//10,0)>>(((ident-1)%10)*3))&7 for ident in wanted}
 assert old_states[2523]!=1,'Awakening already completed; refusing to rewind'
 touched=set()
 for ident,state in wanted.items():
  idx=(ident-1)//10;shift=((ident-1)%10)*3;mask=7<<shift
  packed[idx]=(packed.get(idx,0)&~mask)|(state<<shift);touched.add(idx)
 values=','.join(f'({CHAR},{idx},{packed[idx]})' for idx in sorted(touched))
 completed=','.join(str(q['id']) for q in data['quests'])
 trace=rows('FFDB1',f'SELECT * FROM mission_trace WHERE id={CHAR}')[0];setters=[]
 for slot in range(1,11):
  if trace[f'mission_trace{slot:02}'] in wanted:
   trace[f'mission_trace{slot:02}']=0;trace[f'type{slot:02}']=0
 slot=next((i for i in range(1,11) if trace[f'mission_trace{i:02}']==0),None)
 assert slot is not None,'No free quest tracker slot'
 trace[f'mission_trace{slot:02}']=2523;trace[f'type{slot:02}']=1
 for i in range(1,11):setters.extend([f'mission_trace{i:02}={trace[f"mission_trace{i:02}"]}',f'type{i:02}={trace[f"type{i:02}"]}'])
 sql('FFDB1',f'''BEGIN;
 INSERT INTO final_mission_state1(player_id,index,state) VALUES {values} ON CONFLICT(player_id,index) DO UPDATE SET state=excluded.state;
 UPDATE player_mission_complete_num SET complete_num=greatest(complete_num,1),cycle_finish_state=1 WHERE player_id={CHAR} AND mission_id IN ({completed});
 INSERT INTO player_mission_complete_num(player_id,mission_id,complete_num,cycle_finish_state,cycle_daily_reset)
 SELECT {CHAR},q,1,1,1 FROM unnest(ARRAY[{completed}]) q WHERE NOT EXISTS(SELECT 1 FROM player_mission_complete_num p WHERE p.player_id={CHAR} AND p.mission_id=q);
 UPDATE mission_trace SET {','.join(setters)} WHERE id={CHAR};
 UPDATE player_characters SET level=99,exp={data['exp']},state_flags=(state_flags|15) WHERE id={CHAR} AND account_id=2419;
 COMMIT;''')
 # Existing listings are untouched. Use globally unique new indexes within each AP group.
 marker="note='codex:supplies:v1'"
 stock_query="SELECT * FROM itemmall WHERE note IS DISTINCT FROM 'codex:supplies:v1' ORDER BY item_group,detail_type,item_index,money_unit"
 stock_before=digest('FFAccount',stock_query)
 existing={(r['item_group'],r['detail_type'],r['item_id']) for r in rows('FFAccount',"SELECT item_group,detail_type,item_id FROM itemmall WHERE money_unit=1 AND note IS DISTINCT FROM 'codex:supplies:v1'")}
 indexes={g:int(sql('FFAccount',f"SELECT coalesce(max(item_index),0) FROM itemmall WHERE item_group={g} AND money_unit=1 AND note IS DISTINCT FROM 'codex:supplies:v1';")) for g in [2,3,5]}
 added=[];already=[];inserts=[]
 for item in data['supplies']:
  group,detail,ident=item['item_group'],item['detail_type'],item['id']
  if (group,detail,ident) in existing:already.append(item);continue
  indexes[group]+=1;index=indexes[group];assert index<32767
  inserts.append(f"({ident},{group},{detail},{index},1,1,1,0,0,0,0,-1,1,0,0,'',0,'codex:supplies:v1')")
  added.append(dict(item,index=index))
 statements=f'DELETE FROM itemmall WHERE {marker};'
 if inserts:statements+='INSERT INTO itemmall(item_id,item_group,detail_type,item_index,item_num,money_unit,point,special_price,num_limit,flags,level_limit,gender,sell,not_sell_date,sell_date,message,beginner_only_time,note) VALUES '+','.join(inserts)+';'
 sql('FFAccount','BEGIN;'+statements+'COMMIT;')
 assert digest('FFAccount',stock_query)==stock_before
 actual=rows('FFDB1',f'SELECT index,state FROM final_mission_state1 WHERE player_id={CHAR} ORDER BY index');actual_packed={r['index']:r['state'] for r in actual}
 assert all(((actual_packed[(q-1)//10]>>(((q-1)%10)*3))&7)==state for q,state in wanted.items())
 for old in old_fms:
  idx=old['index'];mask=sum(7<<(((q-1)%10)*3) for q in wanted if (q-1)//10==idx)
  assert (old['state']&~mask)==(actual_packed[idx]&~mask),'Untargeted quest bits changed'
 after=rows('FFDB1',f'SELECT * FROM player_characters WHERE id={CHAR}')[0]
 assert {k:v for k,v in before.items() if k not in ['level','exp','state_flags']}=={k:v for k,v in after.items() if k not in ['level','exp','state_flags']}
 assert inventory=={table:digest('FFDB1',f'SELECT * FROM {table} WHERE player_id={CHAR} ORDER BY id') for table in inventory}
 assert int(sql('FFAccount',f'SELECT count(*) FROM itemmall WHERE {marker};'))==len(added)
 report=dict(backup=str(backup),character='Zrymund',level=99,exp=after['exp'],exp_next_level=data['exp_next_level'],
  completed_quests=len(data['quests']),new_completions=sum(old_states[q['id']]!=1 for q in data['quests']),quest_counts=data['quest_counts'],
  awakening_quest=2523,awakening_state=3,awakening_complete=False,state_flags=after['state_flags'],
  supplies_added=len(added),supply_counts=dict(collections.Counter(i['section'] for i in added)),supplies_already_present=len(already),
  added=added,locations=data['locations'],gold_and_inventory_unchanged=True,other_quest_bits_preserved=True,
  limits='Quest completion flags and feature unlocks applied; ordinary quest item/choice rewards were not retroactively mailed. Client/gameplay verification pending.')
 Path('/root/lv99-supplies-report.json').write_text(json.dumps(report,indent=2));(backup/'report.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k!='added'},indent=2))
finally:subprocess.run(['systemctl','start','aurakingdom'],check=True)
