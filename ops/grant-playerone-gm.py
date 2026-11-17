import datetime,json,os,subprocess
from pathlib import Path
os.umask(0o077)
def sql(db,q):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=q,text=True,capture_output=True,cwd='/tmp',check=True)
 return r.stdout.strip()
assert sql('FFDB1','SELECT quit FROM player_characters WHERE id=50000001 AND account_id=2419;')=='1'
backup=Path('/var/backups/aurakingdom')/('pre-gm-and-mall-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
 for db in ['FFAccount','FFDB1']:
  with (backup/(db+'.dump')).open('wb') as out:
   subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',db],stdout=out,cwd='/tmp',check=True)
 sql('FFAccount',"BEGIN; DELETE FROM gm_tool_accounts WHERE id=2419 OR account_name='playerone'; INSERT INTO gm_tool_accounts(id,account_name,password,privilege) SELECT id,username,password,5 FROM accounts WHERE id=2419 AND username='playerone'; COMMIT;")
 sql('FFDB1','UPDATE player_characters SET privilege=5 WHERE account_id=2419 AND id=50000001;')
 report={'account':'playerone','character':'Zrymund','character_privilege':int(sql('FFDB1','SELECT privilege FROM player_characters WHERE id=50000001;')),'gm_tool_privilege':int(sql('FFAccount',"SELECT privilege FROM gm_tool_accounts WHERE id=2419 AND account_name='playerone';")),'backup':str(backup)}
 Path('/root/playerone-gm-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
finally:
 subprocess.run(['systemctl','start','aurakingdom'],check=True)
