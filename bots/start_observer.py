"""Start temporary human observation only inside the confirmed full lab."""
import subprocess as sp
from pathlib import Path
from lab import assert_inside
assert_inside()
Path('/run/enable-observer').touch()
pids = [p.name for p in Path('/proc').iterdir() if p.name.isdigit() and (p/'comm').exists()
        and (p/'comm').read_text().strip() == 'ZoneServer']
if len(pids) != 1:
    raise SystemExit('Expected one isolated ZoneServer')
log = Path('/var/lib/ak-bot-lab/logs/client-trace.log').open('ab', buffering=0)
process = sp.Popen(['gdb', '-q', '-batch', '--readnever', '/root/hxsy/ZoneServer/ZoneServer',
    '-p', pids[0], '-x', '/opt/ak-bot-prototype/trace_zone.gdb'], stdout=log, stderr=log)
Path('/run/client-trace.pid').write_text(str(process.pid))
print('Sanitized client-behavior trace starting in isolated ZoneServer.')
