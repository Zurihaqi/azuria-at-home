"""Publish only the isolated pilot's saved quest states for reconnect planning."""
import json
import os
from pathlib import Path
import pwd
import subprocess as sp
from lab import assert_inside

assert_inside()
identity = json.loads(Path('/run/pilot/character.json').read_text())
ident = int(identity['id'])
assert identity['name'] == 'AwanBotLab'
query = f"SELECT json_build_object('name',p.given_name,'account',p.account_id,'states',coalesce((SELECT json_agg(t) FROM (SELECT index,state FROM final_mission_state1 WHERE player_id=p.id) t),'[]')) FROM player_characters p WHERE id={ident}"
data = json.loads(sp.check_output(['runuser','-u','postgres','--','psql','-h',
    '/run/postgresql','-X','-At','-d','FFDB1','-c',query],cwd='/').decode())
assert data['name'] == 'AwanBotLab' and data['account'] == 2421
states = {}
for row in data['states']:
    for slot in range(10):
        state = (row['state'] >> (slot * 3)) & 7
        if state:
            states[row['index'] * 10 + slot + 1] = state
path = Path('/run/pilot/quest-history.json')
path.write_text(json.dumps(dict(character_id=ident,states=states)))
path.chmod(0o600)
who = pwd.getpwnam('nobody')
os.chown(path,who.pw_uid,who.pw_gid)
print(f'Read-only saved quest snapshot: {len(states)} states for the lab pilot.')
