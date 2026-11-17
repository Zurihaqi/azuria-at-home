"""Offline append-only Eidolon port, with account-scoped grant and rollback."""
from pathlib import Path
import datetime, hashlib, json, os, re, shutil, subprocess as sp, time
os.umask(0o077)
ACCOUNT, CHAR = 2419, 50000001
STAGE = Path('/tmp/extra-eidolon-port')
DB = Path('/root/hxsy/Data/db')
m = json.loads((STAGE/'manifest.json').read_text())
entries = [e for e in m['files'] if e.get('side') != 'client']

def sql(query):
    p = sp.run(['runuser','-u','postgres','--','psql','-X','-q','-tA',
                '-v','ON_ERROR_STOP=1','-d','FFDB1'], input=query,
               text=True,capture_output=True,cwd='/tmp')
    if p.returncode: raise RuntimeError(p.stderr)
    return p.stdout.strip()

def rows(query):
    return json.loads(sql("SELECT coalesce(json_agg(t),'[]') FROM ("+query+")t"))

def digest(query):
    return hashlib.sha256(json.dumps(rows(query),sort_keys=True).encode()).hexdigest()

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def offline():
    assert sql(f'SELECT quit FROM player_characters WHERE id={CHAR}') == '1', 'Zrymund is online'
    assert sql('SELECT count(*) FROM player_characters WHERE quit=0 AND id NOT IN (50000002,50000003)') == '0', 'A human is online'

def table(path):
    f = path.read_bytes().decode('cp950','surrogateescape').split('|'); n=int(f[2])
    return {int(r[0].strip()):r for i in range(3,len(f)-n,n) if (r:=f[i:i+n])[0].strip().isdigit()}

assert len(m['extra']) == 33
assert sp.run(['systemctl','is-active','--quiet','ak-bot-lab']).returncode != 0
offline()
for e in entries:
    assert sha(DB/e['name']) == e['before'], e['name']+' changed since preparation'
    assert sha(STAGE/e.get('payload',e['name'])) == e['after']
before = rows(f'SELECT * FROM elf WHERE account_id={ACCOUNT} ORDER BY elf_id')
assert len(before)==150 and not ({r['template_id'] for r in before} & set(m['extra']))
backup = Path('/var/backups/aurakingdom')/('extra-eidolons-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700); (backup/'tables').mkdir()
for e in entries: shutil.copy2(DB/e['name'],backup/'tables'/e['name'])
(backup/'manifest.json').write_text(json.dumps(m,indent=2))
created=[]; installed=False
for unit in ('ak-bot-awan','ak-bot-arden'):
    if sp.run(['systemctl','is-active','--quiet',unit]).returncode==0:
        sp.run(['systemctl','stop',unit],check=True,timeout=60)
sp.run(['systemctl','stop','aurakingdom'],check=True,timeout=90)
try:
    for name in ('TicketServer','GatewayServer','LoginServer','MissionServer','WorldServer','ZoneServer'):
        assert sp.run(['pgrep','-x',name],capture_output=True).returncode==1, name+' still running'
    offline()
    before=rows(f'SELECT * FROM elf WHERE account_id={ACCOUNT} ORDER BY elf_id')
    assert len(before)==150
    (backup/'elf-before.json').write_text(json.dumps(before,indent=2))
    with (backup/'FFDB1.dump').open('wb') as out:
        sp.run(['runuser','-u','postgres','--','pg_dump','-Fc','FFDB1'],stdout=out,cwd='/tmp',check=True)
    protected={}
    for name in sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(mission|quest|tutorial|cutscene|trace|node_stream|memories)' ORDER BY tablename").splitlines():
        assert re.fullmatch('[a-z0-9_]+',name)
        protected[name]=digest(f'SELECT * FROM {name} ORDER BY row_to_json({name})::text')
    character=sql(f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHAR}')
    inventory=digest(f'SELECT * FROM inventory1 WHERE player_id={CHAR} ORDER BY id')
    others=digest(f'SELECT * FROM elf WHERE account_id<>{ACCOUNT} ORDER BY elf_id')
    partner=table(STAGE/'S_Partner.ini'); grow=table(DB/'S_PartnerGrow.ini')
    nextid=int(sql('SELECT max(elf_id) FROM (SELECT elf_id FROM elf UNION ALL SELECT elf_id FROM elf_bank UNION ALL SELECT elf_id FROM elf_house)t'))+1
    assert 50000000<nextid<100000000
    used={r['loc'] for r in before if r['type']==1}
    statements=['BEGIN; LOCK TABLE elf IN EXCLUSIVE MODE;']
    for ident in m['extra']:
        r=partner[ident]; ranks=[min(50,(len(col.split(';'))-1)*10) for col in r[59:62]]
        assert int(r[7])==99 and all(v in (0,10,20,30,40,50) for v in ranks)
        slot=next(i for i in range(1000) if i not in used);used.add(slot)
        value=dict(elf_id=nextid,loc=slot,player_id=CHAR,account_id=ACCOUNT,template_id=ident,
                   hp=int(grow[99][30+int(r[32])])+5000,level=99,evo_star=4,love_level=10,love_exp=0,
                   loyalty_value=100,exp=0,spell_level1=ranks[0],spell_level2=ranks[1],spell_level3=ranks[2],
                   emblem_attack=3000,emblem_critical=1000,emblem_recovery=1000,emblem_maxhp=5000,
                   emblem_defence=1000,emblem_dodge=1000,status=0,work_type=0,spell_state=29,
                   dyeing_color=0,surplus_time=0,link_time=0,talk_times=3,skin_data=1,
                   eqpet_buff1=0,eqpet_buff2=0,eqpet_buff3=0,eqpet_buff4=0,eqpet_buff_lock=0,
                   mission_id=0,background_id=1,type=1)
        statements.append('INSERT INTO elf ('+','.join(value)+') VALUES ('+','.join(str(int(v)) for v in value.values())+');')
        created.append(value); nextid+=1
    statements.append('COMMIT;')
    (backup/'apply.sql').write_text('\n'.join(statements))
    (backup/'created.json').write_text(json.dumps(created,indent=2))
    # Install tables before exposing any new character records to native services.
    installed=True
    for e in entries: shutil.copyfile(STAGE/e.get('payload',e['name']),DB/e['name'])
    sql('\n'.join(statements))
    after=rows(f'SELECT * FROM elf WHERE account_id={ACCOUNT} ORDER BY elf_id')
    assert len(after)==183 and len({r['template_id'] for r in after})==183
    byid={r['elf_id']:r for r in after}
    assert all(byid[r['elf_id']]==r for r in before), 'Existing Eidolons changed'
    assert len({(r['type'],r['loc']) for r in after})==183
    for new in created: assert all(byid[new['elf_id']][k]==v for k,v in new.items())
    assert character==sql(f'SELECT row_to_json(t) FROM player_characters t WHERE id={CHAR}')
    assert inventory==digest(f'SELECT * FROM inventory1 WHERE player_id={CHAR} ORDER BY id')
    assert others==digest(f'SELECT * FROM elf WHERE account_id<>{ACCOUNT} ORDER BY elf_id')
    for name,checksum in protected.items():
        assert checksum==digest(f'SELECT * FROM {name} ORDER BY row_to_json({name})::text'),name
    sp.run(['systemctl','start','aurakingdom'],check=True,timeout=90)
    names=('TicketServer','GatewayServer','LoginServer','MissionServer','WorldServer','ZoneServer')
    for attempt in range(45):
        if all(sp.run(['pgrep','-x',n],capture_output=True).returncode==0 for n in names): break
        time.sleep(2)
    else: raise RuntimeError('Not all six native services started')
    report=dict(backup=str(backup),created=33,total=183,level=99,stars=4,affection=10,
                existing_150_unchanged=True,character_unchanged=True,inventory_unchanged=True,
                quest_tables_unchanged=len(protected),other_accounts_unchanged=True,
                six_services_running=True,full_summon_gameplay_verified=False)
    (backup/'report.json').write_text(json.dumps(report,indent=2))
    Path('/root/extra-eidolons-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
except BaseException:
    sp.run(['systemctl','stop','aurakingdom'],timeout=90)
    if installed:
        if created:
            ids=','.join(str(r['elf_id']) for r in created)
            sql(f'DELETE FROM elf WHERE account_id={ACCOUNT} AND elf_id IN ({ids});')
        for e in entries: shutil.copy2(backup/'tables'/e['name'],DB/e['name'])
    sp.run(['systemctl','start','aurakingdom'],timeout=90)
    (backup/'ROLLED-BACK').write_text('Deployment failed; only added rows removed and original tables restored.\n')
    raise
