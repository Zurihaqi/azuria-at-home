import subprocess
q="""SELECT max(item_index),count(*),count(DISTINCT item_index) FROM itemmall WHERE note <> 'codex:gear-catalog:v1'; SELECT max(item_index),count(*) FROM itemmall WHERE note='codex:gear-catalog:v1';"""
for query in q.split(';'):
    if query.strip():
        r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFAccount','-c',query],capture_output=True,text=True,cwd='/tmp');print(r.stdout)
