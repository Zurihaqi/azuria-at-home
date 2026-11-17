import subprocess

def sql(q):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],text=True,capture_output=True,cwd='/tmp');print(r.stdout,r.stderr)
for table in ['player_potential_point','player_weapon_expert','weaponexp','advanced_ability','player_weapon_type']:
 sql('\\d '+table)
 sql('SELECT * FROM '+table+' WHERE player_id=50000001;')
sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(master|ability|expert|weapon|talent)';")
