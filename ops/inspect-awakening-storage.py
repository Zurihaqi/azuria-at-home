import subprocess
for t in ['personal_mission_states','final_mission_state1','player_memories1','mission_trace']:
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c','\\d '+t],text=True,capture_output=True,cwd='/tmp');print(r.stdout,r.stderr)
r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c','SELECT * FROM personal_mission_states WHERE player_id=50000001 LIMIT 6;'],text=True,capture_output=True,cwd='/tmp');print(r.stdout,r.stderr)
