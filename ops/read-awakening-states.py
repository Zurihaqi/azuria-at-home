import subprocess
for q in ['SELECT * FROM personal_mission_states WHERE id=50000001 LIMIT 12;','SELECT * FROM final_mission_state1 WHERE player_id=50000001 ORDER BY index LIMIT 8;','SELECT * FROM mission_trace WHERE id=50000001;']:
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],text=True,capture_output=True,cwd='/tmp');print(r.stdout,r.stderr)
