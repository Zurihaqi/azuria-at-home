import subprocess
for q in ["SELECT schemaname,tablename,rulename,definition FROM pg_rules WHERE tablename LIKE 'player_characters_achievement%';", "SELECT event_object_table,action_statement FROM information_schema.triggers WHERE event_object_table LIKE 'player_characters_achievement%';", "SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_name ~ '(achievement_rank|personal_appellation)' ORDER BY table_name;"]:
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],capture_output=True,text=True,cwd='/tmp');print(r.stdout,r.stderr)
for n in ['']+[str(i) for i in range(1,11)]:
 q=f'SELECT count(*),min(achievement_id),max(achievement_id) FROM player_characters_achievement{n} WHERE account_id=2419;'
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-tA','-d','FFDB1','-c',q],capture_output=True,text=True,cwd='/tmp');print(n or 'base',r.stdout)
