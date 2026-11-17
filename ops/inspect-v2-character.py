import json,subprocess
out={}
queries={
 'equipment':'SELECT id,item_id,player_id,container_index,loc,quality,strengthen,evo_level FROM equipment1 WHERE player_id=50000001 ORDER BY container_index,loc',
 'inventory':'SELECT id,item_id,player_id,container_index,loc FROM inventory1 WHERE player_id=50000001 ORDER BY container_index,loc',
 'points':'SELECT * FROM player_potential_point WHERE player_id=50000001',
 'character':'SELECT id,given_name,level,exp,state_flags,quit,gold,appellation FROM player_characters WHERE id=50000001',
}
for name,q in queries.items():
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input="SELECT coalesce(json_agg(t),'[]') FROM ("+q+') t;',text=True,capture_output=True,cwd='/tmp',check=True)
 out[name]=json.loads(r.stdout)
open('/root/v2-character-before.json','w').write(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
