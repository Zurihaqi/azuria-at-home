import subprocess
for db,q in [('FFAccount','\\d gm_tool_accounts'),('FFDB1',"SELECT column_name,data_type FROM information_schema.columns WHERE table_name ~ '(appellation|flag|panel|title)' ORDER BY table_name;"),('FFDB1',"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(appell|flag|panel|exploit|spell|feature)' ORDER BY tablename;")]:
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d',db,'-c',q],capture_output=True,text=True,cwd='/tmp');print(r.stdout,r.stderr)
