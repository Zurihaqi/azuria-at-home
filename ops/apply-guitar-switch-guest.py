"""Offline, backed-up Guitar conversion; no quest/progression shortcuts."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess as sp
import time

os.umask(0o077)
CHAR=50000001
stage=Path('/root/guitar-switch')
manifest=json.loads((stage/'manifest.json').read_text())

def sql(q):
    r=sp.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp')
    if r.returncode:raise RuntimeError(r.stderr)
    return r.stdout.strip()

def rows(q):return json.loads(sql("SELECT coalesce(json_agg(t),'[]') FROM ("+q+") t"))

def quest_hashes():
    result={}
    for table in sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename").splitlines():
        assert re.fullmatch('[a-z0-9_]+',table)
        data=sql(f"SELECT coalesce(json_agg(t ORDER BY row_to_json(t)::text),'[]') FROM {table} t")
        result[table]=hashlib.sha256(data.encode()).hexdigest()
    return result

assert sql(f'SELECT quit FROM player_characters WHERE id={CHAR}')=='1','Zrymund must be offline'
assert sql(f'SELECT count(*) FROM player_characters WHERE quit=0 AND id NOT IN (50000002,50000003)')=='0','Human players must be offline'
server_files=[f for f in manifest['files'] if f['name'] in ('S_Item.ini','server-T_Item.ini')]
for entry in server_files:
    name=entry['name'].removeprefix('server-')
    assert hashlib.sha256((Path('/root/hxsy/Data/db')/name).read_bytes()).hexdigest()==entry['before'],name+' changed'
    assert hashlib.sha256((stage/entry['name']).read_bytes()).hexdigest()==entry['after']
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/('guitar-switch-'+stamp)
backup.mkdir(mode=0o700)
units=[unit for unit in ('ak-bot-awan','ak-bot-arden') if sp.run(
    ['systemctl','show',unit,'-p','LoadState','--value'],capture_output=True,text=True).stdout.strip()=='loaded']
if units:sp.run(['systemctl','stop',*units],check=True,timeout=60)
sp.run(['systemctl','stop','aurakingdom'],check=True,timeout=60)
success=False
try:
    # A combat-blocked bot logout may leave its persisted quit flag at zero.
    # Verify the stopped native processes, and never relax the human guard.
    assert sql('SELECT count(*) FROM player_characters WHERE quit=0 AND id NOT IN (50000002,50000003)')=='0'
    for process in ('ZoneServer','WorldServer','MissionServer'):
        assert sp.run(['pgrep','-x',process],capture_output=True).returncode==1,process+' is still running'
    with (backup/'FFDB1.dump').open('wb') as out:
        sp.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
    before_quests=quest_hashes()
    character=sql(f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHAR}')
    before_weapon=rows(f'SELECT * FROM player_weapon_type WHERE id={CHAR}')[0]
    assert before_weapon['weapon_type_1']==131072 and before_weapon['weapon_type_2']==32768
    selections=rows(f'SELECT * FROM player_used_upanisad WHERE player_id={CHAR}')[0]
    before_expert=rows(f'SELECT * FROM player_weapon_expert_common_buff WHERE player_id={CHAR} ORDER BY type,expert_id')
    source=rows(f'SELECT * FROM inventory1 WHERE player_id={CHAR} AND item_id=61586 ORDER BY id LIMIT 1')[0]
    (backup/'character-before.json').write_text(character)
    (backup/'weapon-before.json').write_text(json.dumps(before_weapon))
    (backup/'selections-before.json').write_text(json.dumps(selections))
    # Reserve a free instance ID only while all native allocators are stopped.
    # Cold startup preallocates persisted item IDs, including inventory1.
    tables=sql("SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name IN ('id','item_id') GROUP BY table_name HAVING count(DISTINCT column_name)=2 ORDER BY table_name").splitlines()
    maxima=[]
    for table in tables:
        assert re.fullmatch('[a-z0-9_]+',table)
        value=sql(f'SELECT coalesce(max(id),0) FROM "{table}"')
        maxima.append(int(value))
    instance=max(maxima)+1
    assert 50000000<instance<2147483647
    used={(r['container_index'],r['loc']) for r in rows(f'SELECT container_index,loc FROM inventory1 WHERE player_id={CHAR}')}
    # Existing expanded bag 8 is already verified for this character.
    bag,slot=next((8,i) for i in range(20) if (8,i) not in used)
    columns=sql("SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='inventory1'").split(',')
    overrides={'id':str(instance),'item_id':str(manifest['item_id']),'container_index':str(bag),'loc':str(slot),
               'strengthen':'61440','evo_level':'5','durability':'100','cur_maxdurability':'100'}
    expressions=','.join(overrides.get(c,c) for c in columns)
    statements=[f'UPDATE player_weapon_type SET weapon_type_1=32768,weapon_type_2=131072 WHERE id={CHAR};']
    allskills={i:1 for i in manifest['envoy']}
    allskills.update({r['id']:r['rank'] for r in manifest['masteries']})
    signed=lambda i:i-65536 if i>=32768 else i
    unsigned=','.join(str(i) for i in allskills if i>=32768)
    statements.append(f'DELETE FROM player_spells WHERE player_id={CHAR} AND spellmaster_id IN ({unsigned});')
    values=','.join(f'({CHAR},{signed(i)},{rank},1)' for i,rank in allskills.items())
    statements.append(f'INSERT INTO player_spells(player_id,spellmaster_id,spell_order,spell_level) VALUES {values} ON CONFLICT(player_id,spellmaster_id) DO UPDATE SET spell_order=GREATEST(player_spells.spell_order,excluded.spell_order),spell_level=GREATEST(player_spells.spell_level,excluded.spell_level);')
    changes=[]
    byid={r['id']:r for r in manifest['masteries']}
    for number in range(1,7):
        field=f'upanisad{number}';old=selections[field]&65535
        current=byid.get(old)
        if current:
            options=[r for r in manifest['masteries'] if r['type']==current['type'] and r['group']==current['group']]
        else:
            options=[r for r in manifest['masteries'] if r['type']==number+6]
            if number in (1,3):options=[r for r in options if r['id']>=50133]
            group=min(r['group'] for r in options)
            options=[r for r in options if r['group']==group]
        selected=max(options,key=lambda r:r['id'])['id']
        statements.append(f'UPDATE player_used_upanisad SET {field}={selected} WHERE player_id={CHAR};')
        changes.append(dict(slot=number,before=old,after=selected))
    statements.append(f'INSERT INTO player_weapon_expert(player_id,type,level,exp) VALUES({CHAR},0,70,0),({CHAR},1,70,0) ON CONFLICT(player_id,type) DO UPDATE SET level=70,exp=0;')
    statements.append(f'INSERT INTO inventory1({",".join(columns)}) SELECT {expressions} FROM inventory1 WHERE id={source["id"]} AND player_id={CHAR};')
    # Move the existing Guitar from the secondary slot to the now-Guitar main
    # slot. The requested Sovereign Guitar stays in inventory for manual equip.
    main_empty=sql(f'SELECT count(*) FROM equipment1 WHERE player_id={CHAR} AND container_index=0 AND loc=5')=='0'
    if main_empty:
        statements.append(f'UPDATE equipment1 SET loc=5 WHERE player_id={CHAR} AND container_index=0 AND loc=6 AND item_id=33915;')
    for entry in server_files:
        name=entry['name'].removeprefix('server-');target=Path('/root/hxsy/Data/db')/name
        shutil.copy2(target,backup/name);shutil.copy2(stage/entry['name'],target)
    sql('BEGIN;\n'+'\n'.join(statements)+'\nCOMMIT;')
    assert quest_hashes()==before_quests,'Quest data changed'
    assert sql(f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHAR}')==character,'Unrelated character fields changed'
    assert rows(f'SELECT * FROM player_weapon_expert_common_buff WHERE player_id={CHAR} ORDER BY type,expert_id')==before_expert
    learned={r['spellmaster_id']&65535:r['spell_order'] for r in rows(f'SELECT * FROM player_spells WHERE player_id={CHAR}')}
    assert all(learned[i]>=rank for i,rank in allskills.items())
    newitem=rows(f'SELECT id,item_id,container_index,loc,strengthen,evo_level FROM inventory1 WHERE id={instance} AND player_id={CHAR}')[0]
    assert newitem['item_id']==manifest['item_id'] and newitem['strengthen']==61440 and newitem['evo_level']==5
    assert sql(f'SELECT count(*) FROM inventory1 WHERE id={source["id"]} AND item_id=61586')=='1'
    report=dict(backup=str(backup),character='Zrymund',main='Guitar',sub='Whip',envoy_abilities=len(manifest['envoy']),
        mastery_tiers=len(manifest['masteries']),selected_masteries=changes,weapon_specialization_levels=[70,70],
        item=newitem,bag_display_number=bag+1,slot_display_number=slot+1,name=manifest['name'],
        quest_data_unchanged=True,level_currency_and_character_fields_unchanged=True)
    (backup/'report.json').write_text(json.dumps(report,indent=2));Path('/root/guitar-switch-report.json').write_text(json.dumps(report,indent=2))
    success=True
    print(json.dumps(report),flush=True)
finally:
    if success:
        sp.run(['systemctl','start','aurakingdom'],check=True,timeout=60)
    else:
        print('Deployment did not finish: game remains stopped for recovery. Backup: '+str(backup),flush=True)
