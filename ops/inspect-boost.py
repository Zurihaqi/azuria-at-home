import subprocess
def query(db,sql):
    r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d',db,'-c',sql],capture_output=True,text=True,cwd='/tmp')
    print(r.stdout);print(r.stderr)
query('FFDB1','SELECT id,given_name,class_id,level,exp,gold,bind_gold,quit FROM player_characters WHERE id=50000001;')
query('FFDB1',"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(item|inventory|equip|stat|attr|quest|class|spell|level)' ORDER BY tablename;")
for table in ['player_classlist','equipment1','equipment2','inventory1','inventory2','player_spells','personal_mission_states','final_mission_state1']:
    query('FFDB1',f'\\d {table}')
query('FFDB1',"SELECT * FROM player_classlist WHERE player_id=50000001;")
for table in ['player_potential_point','player_coins','advanced_ability','player_weapon_type','player_weapon_expert','weaponexp','bags']:
    query('FFDB1',f'\\d {table}')
query('FFDB1',"SELECT id,item_id,player_id,container_index,loc,strengthen,attr_factor,quality FROM equipment1 WHERE player_id=50000001;")
query('FFDB1',"SELECT id,item_id,player_id,container_index,loc,strengthen,attr_factor,quality FROM inventory1 WHERE player_id=50000001;")
query('FFDB1',"SELECT * FROM player_potential_point WHERE player_id=50000001;")
