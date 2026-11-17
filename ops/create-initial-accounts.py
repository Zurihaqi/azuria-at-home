"""Run in the guest as root; reads protected JSON credentials without logging passwords."""
from pathlib import Path
import hashlib
import json
import subprocess

credentials = json.loads(Path('/root/initial-accounts.json').read_text())
def sql(database, statement):
    result = subprocess.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d',database], input=statement, text=True, capture_output=True, cwd='/tmp')
    if result.returncode:
        raise RuntimeError(f'Database operation failed in {database}; no credential-bearing output displayed')
    return result.stdout.strip()
def quote(value):
    return "'" + str(value).replace("'", "''") + "'"
for account in credentials:
    name, password = account['username'], account['password']
    if sql('FFMember',f'SELECT count(*) FROM tb_user WHERE mid={quote(name)};') != '0':
        raise RuntimeError(f'Account {name} already exists; refusing overwrite')
    digest=hashlib.md5(password.encode()).hexdigest()
    uid=sql('FFMember',f'INSERT INTO tb_user(mid,password,pwd,pvalues) VALUES({quote(name)},{quote(password)},{quote(digest)},0) RETURNING idnum;')
    if not uid.isdigit():
        raise RuntimeError('Unexpected account ID')
    sql('FFAccount',f'INSERT INTO accounts(id,username,password) VALUES({uid},{quote(name)},{quote(password)});')
    if account['role']=='gm':
        sql('FFAccount',f'INSERT INTO gm_tool_accounts(id,account_name,password,privilege) VALUES({uid},{quote(name)},{quote(password)},5);')
    print(f'Created {name} ({account["role"]})')
