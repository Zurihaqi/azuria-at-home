import subprocess
for q in ['\\d player_destiny_road','SELECT * FROM player_destiny_road WHERE player_id=50000001;','SELECT type,count(*),sum(level) FROM player_weapon_expert_common_buff WHERE player_id=50000001 GROUP BY type;']:
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],text=True,capture_output=True,cwd='/tmp');print(r.stdout,r.stderr)
