import subprocess
for db,qs in {'FFAccount':['\\d accounts',"SELECT table_name,column_name FROM information_schema.columns WHERE column_name ~ '(privilege|authority|permission)' ORDER BY table_name;"], 'FFDB1':['\\d player_characters','\\d player_characters_achievement','\\d player_characters_achievement1','\\d player_achievement_coins']}.items():
 for q in qs:
  r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d',db,'-c',q],capture_output=True,text=True,cwd='/tmp');print(r.stdout,r.stderr)
