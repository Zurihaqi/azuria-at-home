"""Restore the first backup into a separate, socket-only PostgreSQL 13 cluster."""
from pathlib import Path
import json
import os
import subprocess

os.umask(0o077)
backup=Path('/var/backups/aurakingdom/20261024T141637Z')
if not (backup/'COMPLETE').exists():
    raise RuntimeError('Backup is not complete')
pgbin=Path('/usr/lib/postgresql/13/bin')
base=Path('/var/lib/postgresql/ak-restore-check')
if base.exists():
    raise RuntimeError('Restore-check directory exists; refusing overwrite')
base.mkdir(mode=0o700)
import pwd
owner=pwd.getpwnam('postgres')
os.chown(base,owner.pw_uid,owner.pw_gid)
socket=base/'socket'
socket.mkdir(mode=0o700)
os.chown(socket,owner.pw_uid,owner.pw_gid)
def run(args,**kwargs):
    r=subprocess.run([str(a) for a in args],capture_output=True,text=True,cwd='/tmp',**kwargs)
    if r.returncode:
        Path('/root/restore-check-error.log').write_text(r.stderr)
        raise RuntimeError(f'{Path(str(args[0])).name} failed; diagnostic retained in restore-check.log')
    return r.stdout.strip()
def aspg(*args):
    return run(['runuser','-u','postgres','--',*args])
def psql(db,statement):
    return run([pgbin/'psql','-X','-h',socket,'-p','55432','-U','postgres','-d',db,'-v','ON_ERROR_STOP=1','-q','-tA'],input=statement)
checked=subprocess.run(['sha256sum','--check','SHA256SUMS'],cwd=backup,capture_output=True,text=True)
if checked.returncode:
    raise RuntimeError('Backup checksum mismatch')
aspg(pgbin/'initdb','-D',base/'data','--auth-local=trust','--auth-host=reject','--locale=C','-E','UTF8')
aspg(pgbin/'pg_ctl','-D',base/'data','-l',base/'postgres.log','-o',f"-c listen_addresses='' -k {socket} -p 55432",'-w','start')
report={}
try:
    globals_sql=(backup/'globals.sql').read_text()
    globals_sql=globals_sql.replace('CREATE ROLE postgres;','')
    psql('postgres',globals_sql)
    for database in ['FFAccount','FFDB1','FFMember']:
        psql('postgres',f'CREATE DATABASE "{database}" TEMPLATE template0;')
        run([pgbin/'pg_restore','--exit-on-error','-h',socket,'-p','55432','-U','postgres','-d',database,backup/f'{database}.dump'])
        report[database]={'public_tables':int(psql(database,"SELECT count(*) FROM pg_tables WHERE schemaname='public';"))}
    report['restored_accounts']=int(psql('FFAccount','SELECT count(*) FROM accounts;'))
    report['restored_characters']=int(psql('FFDB1','SELECT count(*) FROM player_characters;'))
    if report['restored_accounts']!=3:
        raise RuntimeError('Expected the three initial accounts in this backup')
    report['result']='passed_database_restore_in_isolated_cluster'
    report['limits']='No characters existed at backup time. Full VM/gameplay restoration remains untested.'
    (backup/'restore-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
finally:
    aspg(pgbin/'pg_ctl','-D',base/'data','-m','fast','-w','stop')
