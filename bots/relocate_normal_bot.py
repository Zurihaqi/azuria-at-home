"""Only relocate the owner's offline bot; never edit quest/progression records."""
import datetime
import json
import os
from pathlib import Path
import subprocess as sp
from runtime import normal_config, STATE, PROFILE

config = normal_config()
assert os.geteuid() == 0
assert sp.run(['systemctl','is-active','--quiet','ak-bot-' + PROFILE]).returncode != 0
character = json.loads((STATE/'character.json').read_text())
ident = int(character['id'])
expected = {'awan': ('Awan', 50000002), 'arden': ('Arden', 50000003)}[PROFILE]
assert character['name'] == config['character_name'] == expected[0] and ident == expected[1]

def sql(text):
    return sp.check_output(['runuser','-u','postgres','--','psql','-h','/var/run/postgresql',
        '-X','-qAt','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=text.encode(),cwd='/').decode().strip()

before = json.loads(sql(f'SELECT row_to_json(p) FROM player_characters p WHERE id={ident}'))
assert before['given_name']==expected[0] and before['account_id']==config['account_id']
assert before['quit']==1 and before['privilege']==0 and before['node_id']==610
word = int(sql(f'SELECT state FROM final_mission_state1 WHERE player_id={ident} AND index=100'))
assert ((word >> 6) & 7) == 1, 'Final tutorial quest 1003 must already be complete'
plan = dict(character=expected[0],character_id=ident,account_id=config['account_id'],
    from_map=610,to_map=2,destination='Port Skandia',position=[501.128,351.068,-5.67391],
    quest_changes=False,level_changes=False,privilege_changes=False,server_restart=False)
print(json.dumps(plan))
if '--apply' in __import__('sys').argv:
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=Path('/var/backups/aurakingdom')/('bot-location-'+stamp)
    backup.mkdir(mode=0o700)
    os.chmod(backup,0o700)
    (backup/'character-before.json').write_text(json.dumps(before,indent=2))
    os.chmod(backup/'character-before.json',0o600)
    result=sql(f"UPDATE player_characters SET node_id=2,x=501.128,y=351.068,z=-5.67391,face_dir=0,last_normal_area_id=131096,revive_area_id=131085 WHERE id={ident} AND account_id={config['account_id']} AND given_name='{expected[0]}' AND quit=1 AND privilege=0 RETURNING id")
    assert result==str(ident)
    after=json.loads(sql(f'SELECT row_to_json(p) FROM player_characters p WHERE id={ident}'))
    fields={'node_id','x','y','z','face_dir','last_normal_area_id','revive_area_id'}
    assert {k:v for k,v in before.items() if k not in fields} == {k:v for k,v in after.items() if k not in fields}
    plan.update(applied=True,backup=str(backup))
    (STATE/'location-report.json').write_text(json.dumps(plan,indent=2))
    print(json.dumps(plan))
