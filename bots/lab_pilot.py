"""Provision exactly one ordinary account, in the isolated lab database only."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).parent))
from lab import assert_inside

assert_inside()
observer = '--observer' in sys.argv
folder = Path('/run/observer' if observer else '/run/pilot')
folder.mkdir(mode=0o700, exist_ok=True)
identity = folder / 'identity.json'
if identity.exists():
    sys.exit('Pilot identity already exists; no changes.')
name = 'bot_lab_observer' if observer else 'bot_lab_pilot'
password = secrets.token_hex(10)

def sql(db, text):
    proc = subprocess.run(['runuser', '-u', 'postgres', '--',
        '/usr/lib/postgresql/13/bin/psql', '-h', '/run/postgresql', '-X', '-v',
        'ON_ERROR_STOP=1', '-At', '-d', db], input=text.encode(), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, cwd='/')
    if proc.returncode:
        sys.exit('Lab account SQL failed; credentials withheld. Check column constraints.')
    return proc.stdout.decode().strip()

if sql('FFMember', f"SELECT count(*) FROM tb_user WHERE mid='{name}'") != '0':
    sys.exit('Pilot account already exists without identity; refusing duplicate.')
account_id = sql('FFMember', "INSERT INTO tb_user(mid,password,pwd,pvalues) VALUES "
    f"('{name}','{password}','{hashlib.md5(password.encode()).hexdigest()}',0) RETURNING idnum;").splitlines()[0]
sql('FFAccount', f"INSERT INTO accounts(id,username,password) VALUES ({int(account_id)},'{name}','{password}');")
identity.write_text(json.dumps({'username': name, 'password': password, 'account_id': int(account_id)}))
identity.chmod(0o600)
who = pwd.getpwnam('nobody')
os.chown(folder, who.pw_uid, who.pw_gid)
os.chown(identity, who.pw_uid, who.pw_gid)
print('Created one ordinary lab account; no character/GM/progression writes.')
