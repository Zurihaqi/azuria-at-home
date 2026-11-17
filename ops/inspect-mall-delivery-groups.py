import subprocess
for q in ["SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '%itemmall%';", "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name LIKE '%itemmall%' AND column_name ~ '(group|unit|item_id)' ORDER BY table_name,ordinal_position;"]:
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFAccount','-c',q],capture_output=True,text=True,cwd='/tmp');print(r.stdout,r.stderr)
