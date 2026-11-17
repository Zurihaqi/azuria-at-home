import subprocess
q="SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(title|achievement|medal|honor|ability|skill|talent|potential|character|collection|portrait|award)' ORDER BY tablename;"
r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],capture_output=True,text=True,cwd='/tmp');print(r.stdout,r.stderr)
