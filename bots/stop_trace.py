"""Interrupt/detach only the debugger attached to the isolated lab ZoneServer."""
import os
from pathlib import Path
import signal
import time
from lab import assert_inside
assert_inside()
pid = int(Path('/run/client-trace.pid').read_text())
proc = Path('/proc', str(pid))
if not proc.exists():
    raise SystemExit('Trace already stopped')
command = (proc / 'cmdline').read_bytes()
if b'trace_zone.gdb' not in command or (proc / 'comm').read_text().strip() != 'gdb':
    raise SystemExit('Refusing to interrupt an unrelated process')
os.kill(pid, signal.SIGINT)
for _ in range(50):
    if not proc.exists() or (proc / 'stat').read_text().split()[2] == 'Z':
        print('Lab trace detached.')
        break
    time.sleep(.1)
else:
    raise SystemExit('Trace did not detach; not starting another debugger')
