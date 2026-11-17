"""Offline account-specific Eidolon grant; transactional, backed up and bounded."""
from pathlib import Path
import datetime,hashlib,json,os,re,subprocess as sp
os.umask(0o077)
m=json.loads(Path('/tmp/max-eidolons-manifest.json').read_text())
CHAR=m['character_id'];ACCOUNT=m['account_id']
assert (CHAR,ACCOUNT)==(50000001,2419)
def sql(q):
 r=sp.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=q,text=True,capture_output=True,cwd='/tmp')
 if r.returncode:raise RuntimeError(r.stderr)
 return r.stdout.strip()
def rows(q):return json.loads(sql("SELECT coalesce(json_agg(t),'[]') FROM ("+q+")t"))
def digest(q):return hashlib.sha256(json.dumps(rows(q),sort_keys=True).encode()).hexdigest()
def human_offline():
 assert sql(f'SELECT quit FROM player_characters WHERE id={CHAR}')=='1','Zrymund is online'
 assert sql(f'SELECT count(*) FROM player_characters WHERE quit=0 AND id NOT IN (50000002,50000003)')=='0','A human is online'
human_offline()
for name,value in m['sources'].items():
 assert hashlib.sha256((Path('/root/hxsy/Data/db')/name).read_bytes()).hexdigest()==value,name+' changed'
backup=Path('/var/backups/aurakingdom')/('max-eidolons-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
units=[u for u in ('ak-bot-awan','ak-bot-arden') if sp.run(['systemctl','is-active','--quiet',u]).returncode==0]
if units:sp.run(['systemctl','stop',*units],check=True,timeout=60)
sp.run(['systemctl','stop','aurakingdom'],check=True,timeout=60)
for process in ('ZoneServer','WorldServer','MissionServer'):
 assert sp.run(['pgrep','-x',process],capture_output=True).returncode==1,process+' still running'
human_offline()
with (backup/'FFDB1.dump').open('wb') as out:
 sp.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
before=rows(f'SELECT * FROM elf WHERE account_id={ACCOUNT} ORDER BY elf_id')
assert not rows(f'SELECT elf_id FROM elf_bank WHERE account_id={ACCOUNT}')
assert not rows(f'SELECT elf_id FROM elf_house WHERE account_id={ACCOUNT}')
assert all(r['player_id']==CHAR for r in before)
assert len({r['template_id'] for r in before})==len(before),'Duplicate existing partner'
(backup/'elf-before.json').write_text(json.dumps(before,indent=2))
(backup/'manifest.json').write_text(json.dumps(m,indent=2))
protected={}
for table in sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename").splitlines():
 assert re.fullmatch('[a-z0-9_]+',table)
 protected[table]=digest(f'SELECT * FROM {table} ORDER BY row_to_json({table})::text')
character=sql(f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHAR}')
inventory=digest(f'SELECT * FROM inventory1 WHERE player_id={CHAR} ORDER BY id')
others=digest(f'SELECT * FROM elf WHERE account_id<>{ACCOUNT} ORDER BY elf_id')
active=[(r['elf_id'],r['template_id'],r['loc'],r['type']) for r in before if r['type']==0]
assert len(active)==4
nextid=int(sql('SELECT max(elf_id) FROM (SELECT elf_id FROM elf UNION ALL SELECT elf_id FROM elf_bank UNION ALL SELECT elf_id FROM elf_house) t'))+1
assert 50000000<nextid<100000000
used={r['loc'] for r in before if r['type']==1}
existing={r['template_id']:r for r in before}
statements=['BEGIN; LOCK TABLE elf IN EXCLUSIVE MODE;']
created=[]
for spec in m['eidolons']:
 ident=spec['template_id'];existing_row=existing.get(ident)
 if existing_row:
  assignments=','.join(f'{key}={int(value)}' for key,value in spec.items() if key!='template_id')
  statements.append(f'UPDATE elf SET {assignments} WHERE account_id={ACCOUNT} AND template_id={ident};')
 else:
  slot=next(i for i in range(1000) if i not in used);used.add(slot)
  value=dict(elf_id=nextid,loc=slot,player_id=CHAR,account_id=ACCOUNT,
             status=0,work_type=0,spell_state=29,dyeing_color=0,surplus_time=0,
             link_time=0,talk_times=3,skin_data=1,eqpet_buff1=0,eqpet_buff2=0,
             eqpet_buff3=0,eqpet_buff4=0,eqpet_buff_lock=0,mission_id=0,
             background_id=1,type=1,**spec)
  statements.append('INSERT INTO elf ('+','.join(value)+') VALUES ('+','.join(str(int(v)) for v in value.values())+');')
  created.append(dict(id=nextid,template=ident,slot=slot));nextid+=1
statements.append('COMMIT;')
(backup/'apply.sql').write_text('\n'.join(statements))
sql('\n'.join(statements))
after=rows(f'SELECT * FROM elf WHERE account_id={ACCOUNT} ORDER BY elf_id')
assert len(after)==len(m['eidolons'])==150
assert {r['template_id'] for r in after}=={r['template_id'] for r in m['eidolons']}
bytemplate={r['template_id']:r for r in after}
for spec in m['eidolons']:
 assert all(bytemplate[spec['template_id']][k]==v for k,v in spec.items()),spec['template_id']
assert active==[(r['elf_id'],r['template_id'],r['loc'],r['type']) for r in after if r['type']==0]
assert len({(r['type'],r['loc']) for r in after})==150
for old in before:
 new=bytemplate[old['template_id']]
 assert all(new[k]==v for k,v in old.items() if k not in m['eidolons'][0]),old['elf_id']
assert character==sql(f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHAR}')
assert inventory==digest(f'SELECT * FROM inventory1 WHERE player_id={CHAR} ORDER BY id')
assert others==digest(f'SELECT * FROM elf WHERE account_id<>{ACCOUNT} ORDER BY elf_id')
for table,checksum in protected.items():assert checksum==digest(f'SELECT * FROM {table} ORDER BY row_to_json({table})::text'),table
report=dict(backup=str(backup),account=ACCOUNT,character=CHAR,total=len(after),created=len(created),
 active=active,storage=sum(r['type']==1 for r in after),level=99,stars=4,affection=10,
 protected_quest_tables=len(protected),character_unchanged=True,inventory_unchanged=True,
 other_accounts_unchanged=True,native_hp_tests=m['hp_native_tests'],gameplay_verified=False)
(backup/'elf-after.json').write_text(json.dumps(after,indent=2));(backup/'created.json').write_text(json.dumps(created))
(backup/'report.json').write_text(json.dumps(report,indent=2))
Path('/root/max-eidolons-report.json').write_text(json.dumps(report,indent=2))
sp.run(['systemctl','start','aurakingdom'],check=True,timeout=60)
print(json.dumps(report))
