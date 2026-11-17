"""Owner-authorized one-off tutorial skip, only for the offline isolated pilot.

Does not grant future quest completions, GM privileges, levels, gear or currency.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess as sp
from lab import assert_inside
from content import parse_quests

os.umask(0o077)
assert_inside()
assert json.loads(Path('/run/ak-bot-lab.json').read_text())['mode'] == 'authentication-only'
assert not any(Path('/proc', p, 'comm').read_text().strip() in ('ZoneServer', 'WorldServer', 'MissionServer')
               for p in os.listdir('/proc') if p.isdigit() and Path('/proc', p, 'comm').exists())

def sql(text):
    return sp.check_output(['runuser', '-u', 'postgres', '--', 'psql', '-h',
        '/run/postgresql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-d', 'FFDB1'],
        input=text.encode(), cwd='/').decode().strip()

def rows(query):
    return json.loads(sql("SELECT coalesce(json_agg(t),'[]') FROM (" + query + ') t;'))

def fingerprint(query):
    return hashlib.sha256(json.dumps(rows(query), sort_keys=True).encode()).hexdigest()

character = json.loads(Path('/run/pilot/character.json').read_text())
ident = int(character['id'])
assert character['name'] == 'AwanBotLab'
before = rows(f'SELECT * FROM player_characters WHERE id={ident}')[0]
assert before['given_name'] == 'AwanBotLab' and before['account_id'] == 2421
assert before['quit'] == 1 and before['privilege'] == 0
assert before['node_id'] == 610, 'Pilot has already left the tutorial; no edit applied'
source = Path('/root/hxsy/Data/db/S_Mission.ini')
quests = parse_quests(source)
completed = [2001, 1001, 2008, 1003]  # Sword-and-Shield branch only.
assert any(c.name == 'If_FMS' and '1003' in c.args for c in quests[1004].conditions)
assert quests[1004].node == 2
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = Path('/var/lib/ak-bot-lab/snapshots') / ('pre-tutorial-skip-' + stamp)
backup.mkdir(mode=0o700)
with (backup / 'FFDB1.dump').open('wb') as stream:
    sp.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-h', '/run/postgresql',
            '-Fc', 'FFDB1'], stdout=stream, cwd='/', check=True)
(backup / 'character-before.json').write_text(json.dumps(before, indent=2))
assert (backup / 'FFDB1.dump').stat().st_size > 0
other_before = fingerprint(f'SELECT * FROM player_characters WHERE id<>{ident} ORDER BY id')
inventory_before = {t: fingerprint(f'SELECT * FROM {t} WHERE player_id={ident} ORDER BY id')
                    for t in ('inventory1','inventory2','equipment1','equipment2')}
old_fms = rows(f'SELECT index,state FROM final_mission_state1 WHERE player_id={ident} ORDER BY index')
packed = {r['index']: r['state'] for r in old_fms}
touched = set()
for quest in completed:
    index, shift = (quest - 1) // 10, ((quest - 1) % 10) * 3
    packed[index] = (packed.get(index, 0) & ~(7 << shift)) | (1 << shift)
    touched.add(index)
values = ','.join(f'({ident},{idx},{packed[idx]})' for idx in sorted(touched))
ids = ','.join(map(str, completed))
trace = rows(f'SELECT * FROM mission_trace WHERE id={ident}')
setters = []
if trace:
    for slot in range(1, 11):
        field = f'mission_trace{slot:02}'
        if trace[0][field] in completed:
            setters.extend([f'{field}=0', f'type{slot:02}=0'])
statements = [
    f'LOCK TABLE player_characters IN SHARE ROW EXCLUSIVE MODE;',
    f'INSERT INTO final_mission_state1(player_id,index,state) VALUES {values} '
    'ON CONFLICT(player_id,index) DO UPDATE SET state=excluded.state;',
    f'DELETE FROM personal_mission_states WHERE id={ident} AND (index >> 32) IN ({ids});',
    f'UPDATE player_mission_complete_num SET complete_num=greatest(complete_num,1),cycle_finish_state=1 '
    f'WHERE player_id={ident} AND mission_id IN ({ids});',
    f'INSERT INTO player_mission_complete_num(player_id,mission_id,complete_num,cycle_finish_state,cycle_daily_reset) '
    f'SELECT {ident},q,1,1,1 FROM unnest(ARRAY[{ids}]) q WHERE NOT EXISTS '
    f'(SELECT 1 FROM player_mission_complete_num p WHERE p.player_id={ident} AND p.mission_id=q);',
    # Native wake-up buff 45356 transports to S002 event area 24.
    f'UPDATE player_characters SET node_id=2,x=501.128,y=351.068,z=-5.67391,face_dir=0,'
    f'last_normal_area_id={(2 << 16) | 24},revive_area_id={(2 << 16) | 13} '
    f'WHERE id={ident} AND account_id=2421 AND quit=1 AND privilege=0;']
if setters:
    statements.append(f'UPDATE mission_trace SET {",".join(setters)} WHERE id={ident};')
sql('BEGIN;\n' + '\n'.join(statements) + '\nCOMMIT;')
after = rows(f'SELECT * FROM player_characters WHERE id={ident}')[0]
changed = {'node_id','x','y','z','face_dir','last_normal_area_id','revive_area_id'}
assert {k:v for k,v in before.items() if k not in changed} == {k:v for k,v in after.items() if k not in changed}
assert fingerprint(f'SELECT * FROM player_characters WHERE id<>{ident} ORDER BY id') == other_before
assert inventory_before == {t: fingerprint(f'SELECT * FROM {t} WHERE player_id={ident} ORDER BY id') for t in inventory_before}
actual = {r['index']:r['state'] for r in rows(f'SELECT index,state FROM final_mission_state1 WHERE player_id={ident}')}
assert all((actual[(q-1)//10] >> (((q-1)%10)*3)) & 7 == 1 for q in completed)
assert ((actual.get((1004-1)//10,0) >> (((1004-1)%10)*3)) & 7) == 0
for old in old_fms:
    mask = sum(7 << (((q-1)%10)*3) for q in completed if (q-1)//10 == old['index'])
    assert (actual[old['index']] & ~mask) == (old['state'] & ~mask)
report = dict(character=character['name'], character_id=ident, completed=completed,
    node=2, map='Port Skandia', position=[after[k] for k in ('x','y','z')],
    level=after['level'], privilege=after['privilege'], next_quest=1004,
    next_quest_completed=False, backup=str(backup),
    method='Owner-requested database tutorial skip, not autonomous quest completion',
    live_database_untouched=True, inventory_and_other_characters_unchanged=True,
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), login_validation='pending')
Path('/var/lib/ak-bot-lab/tutorial-skip-report.json').write_text(json.dumps(report, indent=2))
(backup / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
