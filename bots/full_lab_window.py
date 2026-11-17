"""Switch the offline server to the isolated full lab, restoring on failure."""
from pathlib import Path
import subprocess as sp
import time

LAB = '/root/ak-bot-explore/lab.py'
query = sp.check_output(['runuser', '-u', 'postgres', '--', '/usr/lib/postgresql/13/bin/psql',
    '-h', '/var/run/postgresql', '-X', '-At', '-d', 'FFDB1', '-c',
    'SELECT count(*) FROM player_characters WHERE quit=0'], cwd='/').decode().strip()
if query != '0':
    raise SystemExit('Human-player protection: live characters are still online; no switch performed.')
if sp.run(['systemctl', 'is-active', '--quiet', 'ak-bot-lab']).returncode == 0:
    sp.run(['python3', LAB, 'stop'], check=True)
    for _ in range(30):
        if sp.run(['systemctl', 'is-active', '--quiet', 'ak-bot-lab']).returncode != 0:
            break
        time.sleep(1)
    else:
        raise SystemExit('Lab did not stop; production untouched.')
sp.run(['systemctl', 'stop', 'aurakingdom'], check=True)
try:
    sp.run(['python3', LAB, 'start-full'], check=True)
except BaseException:
    sp.run(['systemctl', 'start', 'aurakingdom'], check=True)
    raise
print('Full isolated lab starting. Production restart is attached to lab unit cleanup.')
