import subprocess
for table in ['player_spells','advanced_ability','player_classlist','player_weapon_expert_common_buff','weaponexp']:
 for q in ['\\d '+table, 'SELECT * FROM '+table+' WHERE player_id=50000001 LIMIT 12;']:
  r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],capture_output=True,text=True,cwd='/tmp');print(r.stdout,r.stderr)
