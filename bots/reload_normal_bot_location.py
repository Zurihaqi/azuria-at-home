"""One guarded normal-server reload for the requested offline bot move."""
import json
from pathlib import Path
import subprocess as sp
import time
from runtime import normal_config, PROFILE

config=normal_config()
assert sp.run(['systemctl','is-active','--quiet','ak-bot-lab']).returncode != 0
count=sp.check_output(['runuser','-u','postgres','--','psql','-h','/var/run/postgresql',
    '-X','-At','-d','FFDB1','-c','SELECT count(*) FROM player_characters WHERE quit=0'],cwd='/').decode().strip()
assert count=='0','A character is still online; no restart performed'
for name in ('awan', 'arden'):
    assert sp.run(['systemctl','is-active','--quiet','ak-bot-' + name]).returncode != 0
sp.run(['systemctl','stop','aurakingdom'],check=True)
try:
    sp.run(['python3','/opt/ak-bot-prototype/relocate_normal_bot.py','--normal-world','--profile',PROFILE,'--apply'],check=True)
    sp.run(['python3','/opt/ak-bot-prototype/snapshot_normal_quests.py','--normal-world','--profile',PROFILE],check=True)
finally:
    sp.run(['systemctl','start','aurakingdom'],check=True)
print('Normal server reload started; no human character or quest records were edited.',flush=True)
