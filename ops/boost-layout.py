import subprocess
def query(db,sql):
    r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d',db,'-c',sql],capture_output=True,text=True,cwd='/tmp');print(r.stdout);print(r.stderr)
query('FFDB1',"SELECT sequencename,last_value FROM pg_sequences ORDER BY sequencename;")
query('FFDB1',"SELECT column_name,data_type FROM information_schema.columns WHERE table_name='configuration';")
query('FFDB1',"SELECT * FROM configuration;")
query('FFDB1',"SELECT * FROM player_coins WHERE player_id=50000001;")
query('FFMember',"SELECT column_name,data_type FROM information_schema.columns WHERE table_name='tb_user' AND column_name IN ('pvalues','ap','cash','bonus','point');")
