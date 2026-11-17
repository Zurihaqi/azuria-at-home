"""Root-only read-only comparison of public native packet identifiers."""
from pathlib import Path
import json
import re
import struct
from inspect_opcodes import ncid_symbols

processes = [p for p in Path('/proc').iterdir() if p.name.isdigit() and
             (p/'comm').exists() and (p/'comm').read_text().strip() == 'ZoneServer']
assert len(processes) == 1
saved = json.loads(Path('/var/lib/ak-bots/pilot/zone-protocol.json').read_text())
with (processes[0]/'mem').open('rb', buffering=0) as memory:
    for name, address in ncid_symbols(Path('/root/hxsy/ZoneServer/ZoneServer')):
        if 'Hello' in name or 'Echo' in name:
            memory.seek(address)
            print(name, 'live=', struct.unpack('<H', memory.read(2))[0], 'saved=', saved.get(name))
for service in ('WorldServer', 'ZoneServer'):
    paths = sorted(Path('/root/hxsy',service).glob('Test*'), key=lambda p:p.stat().st_mtime)
    if paths:
        with paths[-1].open('rb') as stream:
            stream.seek(max(0, paths[-1].stat().st_size - 2000000))
            lines = stream.read().decode('utf8', errors='replace').splitlines()
        matches = [line[:250] for line in lines if re.search(r'PingAlive|PingEcho',line,re.I)
                   and not re.search(r'pass|secret|ticket|token|credential',line,re.I)]
        print(service, '\n'.join(matches[-5:]))
