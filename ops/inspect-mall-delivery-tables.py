import subprocess
for db in ['FFDB1','FFMember']:
 q="SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND (table_name LIKE '%mall%' OR table_name LIKE '%receiv%') ORDER BY table_name,ordinal_position;"
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d',db,'-c',q],capture_output=True,text=True,cwd='/tmp');print(db,r.stdout,r.stderr)
