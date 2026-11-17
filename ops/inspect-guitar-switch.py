"""Read-only schema and current character evidence for a Guitar class switch."""
import json
import subprocess

def sql(q):
    r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp',check=True)
    return r.stdout.strip()

for table in ('player_characters','player_weapon_type','player_weapon_expert','player_weapon_expert_common_buff','player_used_upanisad','player_spells','inventory1','equipment1'):
    print(table,sql("SELECT string_agg(column_name,',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='"+table+"'"))
for table in ('player_weapon_type','player_weapon_expert','player_weapon_expert_common_buff','player_used_upanisad'):
    field='id' if table=='player_weapon_type' else 'player_id'
    print(table,sql('SELECT coalesce(json_agg(t),\'[]\') FROM '+table+' t WHERE '+field+'=50000001'))
print('character',sql('SELECT row_to_json(t) FROM (SELECT id,given_name,class_id,level,quit,weapon_expert_type,now_equip_page FROM player_characters WHERE id=50000001) t'))
print('equipment',sql('SELECT coalesce(json_agg(t),\'[]\') FROM (SELECT id,item_id,loc,container_index FROM equipment1 WHERE player_id=50000001) t'))
print('custominventory',sql('SELECT coalesce(json_agg(t),\'[]\') FROM (SELECT id,item_id,loc,container_index FROM inventory1 WHERE player_id=50000001 AND item_id>=61586) t'))
print('idallocation',sql("SELECT table_name,column_name,column_default FROM information_schema.columns WHERE (table_name IN ('inventory1','equipment1') AND column_name='id') OR table_name ~ '(sequence|counter|classlist|clone)' ORDER BY table_name,ordinal_position"))
print('sequences',sql("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public'"))
print('learned',sql('SELECT coalesce(json_agg(t),\'[]\') FROM player_spells t WHERE player_id=50000001'))
print('sourceweapon',sql('SELECT row_to_json(t) FROM (SELECT id,item_id,strengthen,evo_level,quality,durability FROM inventory1 WHERE player_id=50000001 AND item_id=61586 LIMIT 1) t'))
