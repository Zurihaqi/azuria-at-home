"""Attach only to the isolated LoginServer, never production."""
from pathlib import Path
import subprocess
from lab import assert_inside
assert_inside()
import sys
service = sys.argv[1] if len(sys.argv) > 1 else 'LoginServer'
if service not in ('LoginServer', 'WorldServer', 'ZoneServer'):
    raise SystemExit('Unsupported lab service')
pids = [p.name for p in Path('/proc').iterdir()
        if p.name.isdigit() and (p / 'comm').exists() and (p / 'comm').read_text().strip() == service]
if len(pids) != 1:
    raise SystemExit('Expected exactly one lab LoginServer')
subprocess.run(['gdb', '-q', '-batch', f'/root/hxsy/{service}/{service}', '-p', pids[0],
                '-x', '/opt/ak-bot-prototype/inspect_login.gdb'], check=True)
