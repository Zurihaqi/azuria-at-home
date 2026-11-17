import subprocess
for db in ['FFDB1','FFAccount']:
 def sql(q):return subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-d',db],input=q,text=True,capture_output=True,cwd='/tmp').stdout.strip()
 tables=sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ 'sky.*tower' ORDER BY tablename").splitlines()
 print(db,tables)
 for name in tables:
  if name in ['sky_tower','sky_tower_info','skytower','skytower_info']:
   print(name,sql(f"SELECT column_name||':'||data_type FROM information_schema.columns WHERE table_name='{name}' ORDER BY ordinal_position"))
   print(sql(f'SELECT row_to_json(t) FROM (SELECT * FROM {name} ORDER BY 1 LIMIT 8) t'))
