"""Offline unlocks, using verified native skill templates and FMS bit packing."""
from pathlib import Path
import datetime,hashlib,json,os,re,subprocess
os.umask(0o077)
CHAR=50000001
def sql(q):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp',check=True)
 return r.stdout.strip()
def rows(table,condition,order):
 return json.loads(sql(f"SELECT coalesce(json_agg(row_to_json(t) ORDER BY {order})::text,'[]') FROM {table} t WHERE {condition};"))
def quest_hashes():
 out={}
 for name in sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename;").splitlines():
  assert re.fullmatch('[a-z0-9_]+',name)
  data=sql(f'SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,\'[]\') FROM "{name}" t;')
  out[name]=hashlib.sha256(data.encode()).hexdigest()
 return out
assert sql(f'SELECT quit FROM player_characters WHERE id={CHAR} AND account_id=2419;')=='1','Character must be offline'
nodes=json.loads(Path('/root/envoy-native-nodes.json').read_text())
masteries=json.loads(Path('/root/skill-masteries-native.json').read_text())
envoy=[n for n in nodes if not n.get('missing')]
assert len(envoy)==50 and len(masteries)==144
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('pre-envoy-mastery-'+stamp);backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
 with (backup/'FFDB1.dump').open('wb') as out:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
 before=quest_hashes();character=sql(f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHAR};')
 weapon_before=rows('player_weapon_expert',f'player_id={CHAR}','type')
 weapon_buff_before=rows('player_weapon_expert_common_buff',f'player_id={CHAR}','type,expert_id')
 selections=rows('player_used_upanisad',f'player_id={CHAR}','player_id')[0]
 before_fms=rows('final_mission_state1',f'player_id={CHAR}','index')
 before_trace=rows('mission_trace',f'id={CHAR}','id')[0]
 (backup/'before.json').write_text(json.dumps({'quest_hashes':before,'selections':selections,'fms':before_fms,'trace':before_trace},indent=2))
 skills={n['id']:1 for n in envoy}
 skills.update({m['id']:m['max_order'] for m in masteries})
 def signed(i):return i-65536 if i>=32768 else i
 values=','.join(f'({CHAR},{signed(i)},{rank},1)' for i,rank in skills.items())
 # Normalize only these targeted IDs to the signed-short representation used by native saves.
 unsigned=','.join(str(i) for i in skills if i>=32768)
 statements=[f'DELETE FROM player_spells WHERE player_id={CHAR} AND spellmaster_id IN ({unsigned});',
 f'INSERT INTO player_spells(player_id,spellmaster_id,spell_order,spell_level) VALUES {values} ON CONFLICT(player_id,spellmaster_id) DO UPDATE SET spell_order=excluded.spell_order;']
 selected_changes=[]
 byid={m['id']:m for m in masteries}
 for slot in range(1,7):
  field=f'upanisad{slot}';old=selections[field]&65535;current=byid.get(old)
  if current:
   family=[m for m in masteries if m['type']==current['type'] and m['group']==current['group']]
   highest=max(family,key=lambda m:m['id'])
   statements.append(f'UPDATE player_used_upanisad SET {field}={highest["id"]} WHERE player_id={CHAR};')
   selected_changes.append({'slot':slot,'name':current['name'],'before':old,'after':highest['id']})
 quest=2508;idx=(quest-1)//10;shift=((quest-1)%10)*3;mask=7<<shift
 oldrow=next((x for x in before_fms if x['index']==idx),None);oldpacked=oldrow['state'] if oldrow else 0
 oldstate=(oldpacked>>shift)&7
 # State 3 is the exact accepted state used by native TC_AcceptMission; state 1 means completed.
 if oldstate==1:raise RuntimeError('Gaia Gate is already completed; identify the current awakening-chain stage before changing it')
 packed=(oldpacked&~mask)|(3<<shift)
 statements.append(f'INSERT INTO final_mission_state1(player_id,index,state) VALUES({CHAR},{idx},{packed}) ON CONFLICT(player_id,index) DO UPDATE SET state=excluded.state;')
 trace_slot=None
 if quest not in [before_trace[f'mission_trace{i:02}'] for i in range(1,11)]:
  trace_slot=next((i for i in range(1,11) if before_trace[f'mission_trace{i:02}']==0),None)
  if trace_slot:statements.append(f'UPDATE mission_trace SET mission_trace{trace_slot:02}={quest},type{trace_slot:02}=1 WHERE id={CHAR};')
 sql('BEGIN;\n'+'\n'.join(statements)+'\nCOMMIT;')
 after=quest_hashes()
 assert {k:v for k,v in before.items() if k not in ['final_mission_state1','mission_trace']}=={k:v for k,v in after.items() if k not in ['final_mission_state1','mission_trace']}
 after_fms=rows('final_mission_state1',f'player_id={CHAR}','index')
 assert [r for r in before_fms if r['index']!=idx]==[r for r in after_fms if r['index']!=idx]
 actual=next(r['state'] for r in after_fms if r['index']==idx)
 assert actual==packed and (actual&~mask)==(oldpacked&~mask)
 assert weapon_before==rows('player_weapon_expert',f'player_id={CHAR}','type')
 assert weapon_buff_before==rows('player_weapon_expert_common_buff',f'player_id={CHAR}','type,expert_id')
 assert character==sql(f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHAR};')
 learned={r['spellmaster_id']:r['spell_order'] for r in rows('player_spells',f'player_id={CHAR}','spellmaster_id')}
 assert all(learned[signed(i)]==rank for i,rank in skills.items())
 report={'character':'Zrymund','backup':str(backup),'envoy_abilities':50,'unsupported_envoy_option_skipped':50737,'mastery_tier_unlocks':144,'mastery_choices':36,'selected_masteries_upgraded':selected_changes,'weapon_mastery_records_unchanged':True,'awakening_quest':{'id':2508,'name':'Lv99 Gaia Gate','state':3,'previous_state':oldstate,'trace_slot_added':trace_slot},'other_quests_unchanged':True,'character_level_and_gold_unchanged':True,'validation':'All intended DB records and exact quest-bit isolation verified; in-game loading and UI verification pending'}
 Path('/root/envoy-mastery-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
finally:
 subprocess.run(['systemctl','start','aurakingdom'],check=True)
