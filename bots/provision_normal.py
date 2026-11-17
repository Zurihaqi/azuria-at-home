"""Provision exactly one ordinary live-world bot, explicitly requested by owner."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import struct
import subprocess as sp
from inspect_opcodes import ncid_symbols
from runtime import PROFILE

assert os.geteuid() == 0
assert sp.run(['systemctl','is-active','--quiet','aurakingdom']).returncode == 0
assert sp.run(['systemctl','is-active','--quiet','ak-bot-lab']).returncode != 0
os.umask(0o077)
if sp.run(['id','akbots'],stdout=sp.DEVNULL,stderr=sp.DEVNULL).returncode:
    sp.run(['useradd','--system','--home-dir','/var/lib/ak-bots','--shell','/usr/sbin/nologin','akbots'],check=True)
who = pwd.getpwnam('akbots')
base = Path('/var/lib/ak-bots')
username = 'ardenbot' if PROFILE=='arden' else 'awanbot'
character_name = 'Arden' if PROFILE=='arden' else 'Awan'
state = base / ('arden' if PROFILE=='arden' else 'pilot')
state.mkdir(parents=True,exist_ok=True)
base.chmod(0o755)
state.chmod(0o700)
os.chown(state,who.pw_uid,who.pw_gid)
config_dir = Path('/etc/ak-bots');config_dir.mkdir(exist_ok=True);config_dir.chmod(0o755)

def sql(db, text):
    return sp.check_output(['runuser','-u','postgres','--','psql','-h','/var/run/postgresql',
        '-X','-qAt','-v','ON_ERROR_STOP=1','-d',db],input=text.encode(),cwd='/').decode().strip()

identity_path = state / 'identity.json'
if not identity_path.exists():
    assert sql('FFMember',f"SELECT count(*) FROM tb_user WHERE mid='{username}'") == '0'
    assert sql('FFAccount',f"SELECT count(*) FROM accounts WHERE username='{username}'") == '0'
    assert sql('FFDB1',f"SELECT count(*) FROM player_characters WHERE given_name='{character_name}'") == '0'
    password = secrets.token_hex(10)  # Native account column is varchar(20).
    account = int(sql('FFMember',"INSERT INTO tb_user(mid,password,pwd,pvalues) VALUES "
        f"('{username}','{password}','{hashlib.md5(password.encode()).hexdigest()}',0) RETURNING idnum"))
    sql('FFAccount',f"INSERT INTO accounts(id,username,password) VALUES ({account},'{username}','{password}')")
    identity_path.write_text(json.dumps(dict(username=username,password=password,account_id=account)))
    os.chown(identity_path,who.pw_uid,who.pw_gid)
identity = json.loads(identity_path.read_text())
config = dict(enabled=True,username=username,account_id=identity['account_id'],character_name=character_name,
              authorization='Owner explicitly requested the normal world on 2026-10-26',experimental=True)
config_path = config_dir/('arden-world.json' if PROFILE=='arden' else 'normal-world.json');config_path.write_text(json.dumps(config,indent=2));config_path.chmod(0o644)
for service,destination in [('LoginServer','protocol.json'),('WorldServer','world-protocol.json'),('ZoneServer','zone-protocol.json')]:
    pids = [p for p in Path('/proc').iterdir() if p.name.isdigit() and (p/'comm').exists()
            and (p/'comm').read_text().strip()==service]
    assert len(pids)==1
    ids = {}
    with (pids[0]/'mem').open('rb',buffering=0) as stream:
        for name,address in ncid_symbols(Path('/root/hxsy',service,service)):
            stream.seek(address);ids[name]=struct.unpack('<H',stream.read(2))[0]
    path = state/destination;path.write_text(json.dumps(ids));path.chmod(0o600);os.chown(path,who.pw_uid,who.pw_gid)
print(json.dumps(dict(account_id=identity['account_id'],username=username,character_name=character_name,
                     credentials='private',game_server_restarted=False)))
