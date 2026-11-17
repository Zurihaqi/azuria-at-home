"""Deploy the shared activity controller, with bot-only restarts and backups."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import py_compile
import re
import shutil
import subprocess as sp
import sys

assert os.geteuid() == 0
flags = [arg for arg in sys.argv[1:] if arg.startswith('--')]
assert set(flags) <= {'--quest-framework-only', '--battle-framework', '--spend-potential', '--grind'}
profiles = [arg for arg in sys.argv[1:] if not arg.startswith('--')] or ['awan', 'arden']
assert profiles and len(set(profiles)) == len(profiles) and set(profiles) <= {'awan', 'arden'}
assert sp.run(['systemctl', 'is-active', '--quiet', 'aurakingdom']).returncode == 0
assert sp.run(['systemctl', 'is-active', '--quiet', 'ak-bot-lab']).returncode != 0
root = Path('/opt/ak-bot-prototype')
stage = root / 'activity-staging'
files = ('assist.py', 'combat.py', 'probe_login.py', 'social.py', 'objectives.py', 'inventory.py', 'portals.py', 'quest_engine.py', 'movement.py', 'battle.py', 'evasion.py', 'crafting.py', 'content.py', 'worldmap.py', 'potential.py', 'grind.py', 'bot_control.py')
for name in files:
    py_compile.compile(str(stage / name), doraise=True)
sys.path.insert(0, str(root))
sys.path.insert(0, str(stage))
from assist import hostile_templates, resource_templates
import grind
hostile = sorted(hostile_templates('/root/hxsy/Data/db/S_Biology.ini'))
assert 40323 in hostile and 10210 not in hostile
mob_catalog = grind.catalog_from_biology('/root/hxsy/Data/db/S_Biology.ini')
assert mob_catalog[40327]['hp'] == 301 and 41071 not in mob_catalog and 41165 not in mob_catalog
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = Path('/var/backups/ak-bots') / ('shared-activity-' + stamp)
backup.mkdir(parents=True, mode=0o700)
for name in files:
    if (root / name).exists():
        shutil.copy2(root / name, backup / name)
units = ['ak-bot-' + profile for profile in profiles]
loaded = [unit for unit in units if sp.run(
    ['systemctl', 'show', unit, '-p', 'LoadState', '--value'], text=True,
    capture_output=True, check=False).stdout.strip() == 'loaded']
if loaded:
    sp.run(['systemctl', 'stop', *loaded], check=True, timeout=50)
for unit in ('ak-bot-' + profile for profile in profiles):
    assert sp.run(['systemctl', 'is-active', '--quiet', unit]).returncode != 0
for name in files:
    shutil.copy2(stage / name, root / name)
    (root / name).chmod(0o644)
catalog = root / 'maps/hostile-templates.json'
if catalog.exists():
    shutil.copy2(catalog, backup / catalog.name)
catalog.write_text(json.dumps(hostile))
catalog.chmod(0o644)
resources = sorted(resource_templates('/root/hxsy/Data/db/S_Biology.ini'))
assert 40337 in resources and 41165 not in resources
(root / 'maps/resource-templates.json').write_text(json.dumps(resources))
(root / 'maps/resource-templates.json').chmod(0o644)
node_text = Path('/root/hxsy/Data/db/S_Node.ini').read_bytes().decode('cp950', errors='replace')
public_maps = [int(row[0]) for block in re.split(r'(?m)(?=^\d+\|)', node_text)[1:]
               if len(row := block.rstrip().split('|')) > 10 and row[9] in ('1', '2')]
(root / 'maps/public-maps.json').write_text(json.dumps(public_maps))
(root / 'maps/public-maps.json').chmod(0o644)
item_text = Path('/root/hxsy/Data/db/S_Item.ini').read_bytes().decode('cp950', errors='replace')
gear_catalog = {}
for block in re.split(r'(?m)(?=^\d+\|)', item_text)[1:]:
    row = block.rstrip().split('|')
    if len(row) <= 43 or row[8] not in ('1', '2', '3', '4', '5', '8'):
        continue
    if not 10000 <= int(row[0]) < 30000 or not row[13].isdigit() or row[12] not in ('', '-1'):
        continue
    if any(row[index] for index in range(14, 19)):
        continue
    power = row[39] if row[8] == '8' else row[43]
    if power.isdigit() and int(power) > 0:
        gear_catalog[row[0]] = dict(type=int(row[8]), level=int(row[13]), score=int(power))
(root / 'maps/gear-catalog.json').write_text(json.dumps(gear_catalog))
(root / 'maps/gear-catalog.json').chmod(0o644)
(root / 'maps/mob-catalog.json').write_text(json.dumps(mob_catalog))
(root / 'maps/mob-catalog.json').chmod(0o644)
import worldmap
world_index = worldmap.write_index(root / 'maps')
import time
time.sleep(30)  # Native world cleanup after a combat-blocked logout/socket close.
launch = {}
for profile, state, args in (
    ('awan', 'pilot', ['--quests', '--ensure-gear']),
    ('arden', 'arden', ['--profile', 'arden', '--companion']),
):
    # Recorded so bot_control.py (dashboard Start) replays exactly this launch.
    launch[profile] = dict(args=args, flags=flags)
    if profile not in profiles:
        continue
    log = '/var/lib/ak-bots/' + state + '/session.log'
    sp.run(['systemd-run', '--collect', '--unit=ak-bot-' + profile, '--uid=akbots',
            '--property=NoNewPrivileges=yes', '--property=WorkingDirectory=' + str(root),
            '--property=StandardOutput=append:' + log,
            '--property=StandardError=append:' + log,
            '/usr/bin/python3', '-u', str(root / 'probe_login.py'), '--normal-world',
            *args, *flags, '--chat', '--continuous', '--encounter-learning'], check=True)
    # Stagger normal player logins.
    import time
    time.sleep(3)
report = dict(backup=str(backup), game_restarted=False, database_edits=False,
              files={name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files},
              hostile_templates=len(hostile), world_templates=len(world_index['templates']),
              launch=launch)
(backup / 'deployment.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
