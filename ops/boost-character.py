"""One-off, offline-only boost for Zrymund; deliberately preserves quest tables."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import subprocess

os.umask(0o077)
CHARACTER=50000001
ACCOUNT=2419
ITEMS=[33917,33937,22799,33950,33951,33952,33953,33954,22956,22957,22958,22959,22960,22977,22976,22978,32798,32799]
def sql(db,text):
    r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',db],input=text,text=True,capture_output=True,cwd='/tmp')
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()
def quests():
    names=sql('FFDB1',"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename;").splitlines()
    result={}
    for name in names:
        assert re.fullmatch('[a-z0-9_]+',name)
        data=sql('FFDB1',f'SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,\'[]\') FROM "{name}" t;')
        result[name]=hashlib.sha256(data.encode()).hexdigest()
    return result

current=json.loads(sql('FFDB1',f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHARACTER};'))
if current['given_name']!='Zrymund' or current['account_id']!=ACCOUNT or current['quit']!=1:
    raise RuntimeError('Expected Zrymund offline; refusing edit')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/aurakingdom')/f'pre-boost-{stamp}'
backup.mkdir(mode=0o700)
subprocess.run(['systemctl','stop','aurakingdom'],check=True)
try:
    for database in ['FFDB1','FFMember']:
        with (backup/f'{database}.dump').open('wb') as output:
            subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',database],stdout=output,check=True,cwd='/tmp')
    before=quests()
    (backup/'quests-before.json').write_text(json.dumps(before,indent=2))
    (backup/'character-before.json').write_text(json.dumps(current,indent=2))
    # Full EXP at the last row supported by this installation's S_Level table.
    statements=[f'UPDATE player_characters SET level=150,exp=4199999999,skill_point=1000,gold=1000000000,bind_gold=1000000000,dust=1000000,colosseum_gold=1000000 WHERE id={CHARACTER} AND account_id={ACCOUNT};',
        f'UPDATE player_potential_point SET point1=99,point2=99,point3=99,point4=99,point5=99,point6=99,atk=1000,def=1000 WHERE player_id={CHARACTER};',
        # Preserve starter item IDs so a quest requiring its original item remains possible.
        f'UPDATE equipment1 SET strengthen=61440,modified_attack=1000000,modified_maxhp=1000000,modified_defence=100000,modified_critical=100000,modified_dodge=100000 WHERE player_id={CHARACTER} AND container_index=0 AND loc IN (2,5,7,8);']
    for item in ITEMS:
        statements.append(f"INSERT INTO sys_mail_queue(receiver_id,clone_item_id,item_id,sender_name,title,content,durability,cur_maxdurability,strengthen,bind,item_level,modified_attack,modified_maxhp,modified_defence,modified_critical,modified_dodge) VALUES({CHARACTER},0,{item},'Server Admin','Endgame gear +30','Requested character boost; quests preserved.',100,100,61440,1,1,1000000,1000000,100000,100000,100000);")
    sql('FFDB1','BEGIN;\n'+'\n'.join(statements)+'\nCOMMIT;')
    sql('FFMember',f'BEGIN; UPDATE tb_user SET pvalues=1000000000,bonus=1000000000 WHERE idnum={ACCOUNT}; COMMIT;')
    after=quests()
    if after!=before:
        raise RuntimeError('Quest fingerprint mismatch; backup retained for recovery')
    report={'character':'Zrymund','character_id':CHARACTER,'account_id':ACCOUNT,'level':150,'exp':4199999999,'gold_base_units':1000000000,'bound_gold_base_units':1000000000,'shop_points':1000000000,'bonus_points':1000000000,'stat_allocations':[99]*6,'spare_attack_points':1000,'spare_defence_points':1000,'equipment_rank':30,'equipment_strengthen_encoded':61440,'mailed_item_ids':ITEMS,'quest_tables_verified_unchanged':list(before),'backup':str(backup),'limits':'Currency is a large finite balance. Gear/stat effects require client validation.'}
    (backup/'boost-report.json').write_text(json.dumps(report,indent=2))
    Path('/root/latest-boost-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
finally:
    subprocess.run(['systemctl','start','aurakingdom'],check=True)
