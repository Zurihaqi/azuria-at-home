"""Guest-only password rotation. Credential payload and command output stay private."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess
os.umask(0o077)
payload=Path('/root/password-change.json');data=json.loads(payload.read_text())
assert data['username']=='playerone'
def quote(value):return "'"+str(value).replace("'","''")+"'"
def sql(db,q):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=q,text=True,capture_output=True,cwd='/tmp')
 if r.returncode:raise RuntimeError('Password database operation failed; output suppressed')
 return r.stdout.strip()
assert sql('FFDB1','SELECT quit FROM player_characters WHERE account_id=2419 AND id=50000001')=='1'
assert sql('FFAccount',"SELECT count(*) FROM accounts WHERE id=2419 AND username='playerone'")=='1'
backup=Path('/var/backups/aurakingdom')/('pre-password-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir(mode=0o700)
for db in ['FFAccount','FFMember']:
 with (backup/(db+'.dump')).open('wb') as output:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',db],stdout=output,cwd='/tmp',check=True)
password=quote(data['password']);digest=quote(hashlib.md5(data['password'].encode()).hexdigest())
sql('FFMember',f"UPDATE tb_user SET password={password},pwd={digest} WHERE idnum=2419 AND mid='playerone';")
sql('FFAccount',f"BEGIN; UPDATE accounts SET password={password} WHERE id=2419 AND username='playerone'; UPDATE gm_tool_accounts SET password={password} WHERE id=2419 AND account_name='playerone'; COMMIT;")
assert sql('FFMember',f"SELECT count(*) FROM tb_user WHERE idnum=2419 AND password={password} AND pwd={digest}")=='1'
assert sql('FFAccount',f"SELECT count(*) FROM accounts WHERE id=2419 AND password={password}")=='1'
assert sql('FFAccount',f"SELECT count(*) FROM gm_tool_accounts WHERE id=2419 AND password={password} AND privilege=5")=='1'
payload.unlink();print('playerone password updated and verified in game login and GM account stores.')
