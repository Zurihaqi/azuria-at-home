from pathlib import Path
import hashlib,json,os,subprocess
os.umask(0o077)
def sql(text):
    r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=text,text=True,capture_output=True,cwd='/tmp')
    if r.returncode: raise RuntimeError(r.stderr)
    return r.stdout.strip()
if sql('SELECT quit FROM player_characters WHERE id=50000001;')!='1':
    raise RuntimeError('Character must be offline')
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
    # Isolate high-level client compatibility from equipment and stat modifications.
    sql('''BEGIN;
UPDATE player_characters SET level=99,exp=0,skill_point=0 WHERE id=50000001 AND account_id=2419;
UPDATE player_potential_point SET point1=0,point2=0,point3=0,point4=0,point5=0,point6=0,atk=0,def=0 WHERE player_id=50000001;
UPDATE equipment1 SET strengthen=0,modified_attack=0,modified_maxhp=0,modified_defence=0,modified_critical=0,modified_dodge=0 WHERE player_id=50000001 AND container_index=0 AND loc IN (2,5,7,8);
DELETE FROM sys_mail_queue WHERE receiver_id=50000001 AND title='Endgame gear +30' AND state='New';
COMMIT;''')
    before=json.loads(Path('/var/backups/aurakingdom/pre-boost-20261024T144300Z/quests-before.json').read_text())
    after={}
    for name in before:
        data=sql(f'SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,\'[]\') FROM "{name}" t;')
        after[name]=hashlib.sha256(data.encode()).hexdigest()
    report={'character':'Zrymund','test_level':99,'gold_base_units':1000000000,'gear_and_stat_modifications':'reverted to original values','pending_incompatible_gear_mail':'removed','quest_tables_unchanged':after==before,'changed_quest_tables':[name for name in before if before[name]!=after[name]]}
    Path('/root/boost-recovery-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
finally:
    subprocess.run(['systemctl','start','aurakingdom'],check=True)
