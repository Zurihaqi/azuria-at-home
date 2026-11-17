import subprocess
q="SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND (table_name ~ '(upan|mastery)' OR column_name ~ '(upan|mastery)') ORDER BY table_name,ordinal_position;"
r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],text=True,capture_output=True,cwd='/tmp');print(r.stdout,r.stderr)
