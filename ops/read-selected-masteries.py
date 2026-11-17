import subprocess
for q in ['SELECT * FROM player_used_upanisad WHERE player_id=50000001;','SELECT index,state FROM final_mission_state1 WHERE player_id=50000001 AND index BETWEEN 250 AND 252;']:
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],text=True,capture_output=True,cwd='/tmp');print(r.stdout,r.stderr)
