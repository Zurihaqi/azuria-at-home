from pathlib import Path
import datetime,json,os,subprocess
os.umask(0o077)
def sql(q):
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp',check=True)
 return r.stdout.strip()
before=json.loads(sql('SELECT row_to_json(t) FROM player_characters t WHERE id=50000001 AND account_id=2419;'))
assert before['quit']==1 and before['given_name']=='Zrymund','Character must be offline'
backup=Path('/var/backups/aurakingdom')/('pre-gold-fix-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
 with (backup/'FFDB1.dump').open('wb') as out:subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
 sql('UPDATE player_characters SET gold=1000000,bind_gold=0 WHERE id=50000001 AND account_id=2419;')
 after=json.loads(sql('SELECT row_to_json(t) FROM player_characters t WHERE id=50000001 AND account_id=2419;'))
 changed=[k for k in before if before[k]!=after[k]]
 assert set(changed)<=set(['gold','bind_gold'])
 report={'character':'Zrymund','gold':1000,'gold_base_units':after['gold'],'bound_gold':after['bind_gold'],'base_units_per_gold':1000,'changed_character_fields':changed,'backup':str(backup),'source':'CItemFactory::NormalizeGoldString divides gold by 1000'}
 Path('/root/gold-fix-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
finally:
 subprocess.run(['systemctl','start','aurakingdom'],check=True)
