"""Read native NCID globals from an isolated process without pausing it.

An ELF64 symbol reader avoids loading ZoneServer's very large DWARF into GDB.
This is a lab-only observation tool, not part of the future bot runtime.
"""
import json
from pathlib import Path
import re
import struct
import sys
from lab import assert_inside


def ncid_symbols(path):
    with path.open('rb') as f:
        header = f.read(64)
        if header[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', header, 16)[0] != 2:
            raise ValueError('Expected non-PIE little-endian ELF64')
        offset = struct.unpack_from('<Q', header, 40)[0]
        stride, count = struct.unpack_from('<HH', header, 58)
        f.seek(offset)
        raw = f.read(stride * count)
        sections = [struct.unpack_from('<IIQQQQIIQQ', raw, i * stride) for i in range(count)]
        for section in sections:
            if section[1] != 2:
                continue
            strings = sections[section[6]]
            f.seek(strings[4])
            names = f.read(strings[5])
            f.seek(section[4])
            table = f.read(section[5])
            for at in range(0, len(table), section[9]):
                name_at, _, _, _, address, size = struct.unpack_from('<IBBHQQ', table, at)
                name = names[name_at:names.find(b'\0', name_at)].decode('ascii', errors='replace')
                match = re.search(r'(CN[CE]_\w+)EE4NCIDE$', name)
                if match and size == 2:
                    yield match.group(1), address


if __name__ == '__main__':
    assert_inside()
    service = sys.argv[1]
    if service not in ('LoginServer', 'WorldServer', 'ZoneServer'):
        raise SystemExit('Unsupported service')
    pids = [p.name for p in Path('/proc').iterdir() if p.name.isdigit() and
            (p / 'comm').exists() and (p / 'comm').read_text().strip() == service]
    if len(pids) != 1:
        raise SystemExit('Expected one isolated service')
    ids = {}
    with Path('/proc', pids[0], 'mem').open('rb', buffering=0) as memory:
        for name, address in ncid_symbols(Path('/root/hxsy', service, service)):
            memory.seek(address)
            ids[name] = struct.unpack('<H', memory.read(2))[0]
    destination = {'LoginServer': 'protocol.json', 'WorldServer': 'world-protocol.json',
                   'ZoneServer': 'zone-protocol.json'}[service]
    Path('/run/pilot', destination).write_text(json.dumps(ids, indent=2))
    print(f'{service}: observed {len(ids)} native NCID globals; no process pause or memory writes.')
    print(json.dumps({k:v for k,v in ids.items() if k.startswith('CNE_CZ_') and any(x in k for x in
        ('Hello','ReceiveTicket','Login','Ready','Enter','Move','Position','Heartbeat'))}, indent=2))
