import subprocess
for table in ['personal_appellation','player_appellation','account_panel']:
 for q in ['\\d '+table,'SELECT * FROM '+table+' LIMIT 3;']:
  r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],capture_output=True,text=True,cwd='/tmp');print(r.stdout,r.stderr)
