"""Read only the two dedicated bots' ping counters; never pause/write the server."""
from pathlib import Path
import json
import struct

processes = [p for p in Path('/proc').iterdir() if p.name.isdigit() and
             (p/'comm').exists() and (p/'comm').read_text().strip() == 'ZoneServer']
assert len(processes) == 1
with (processes[0]/'mem').open('rb', buffering=0) as memory:
    def read(address, code):
        memory.seek(address)
        return struct.unpack('<' + code, memory.read(struct.calcsize('<' + code)))[0]
    server = read(0x1685ea0, 'Q')
    buckets, count = read(server + 0xbd0, 'Q'), read(server + 0xbd8, 'Q')
    assert 0 < count < 1000000
    for name, ident in (('Awan', 50000002), ('Arden', 50000003)):
        item = read(buckets + (ident % count) * 8, 'Q')
        result = dict(name=name, online=False)
        for _ in range(32):
            if not item:
                break
            if read(item, 'I') == ident:
                character = read(item + 8, 'Q')
                assert read(character + 0x38, 'I') == ident
                event = read(character + 0x1c80, 'Q')
                result.update(online=True, pending_ping=read(character + 0x3a20, 'h'))
                if event:
                    result.update(last_ping=read(event + 0x30, 'i'), last_echo=read(event + 0x34, 'i'))
                break
            item = read(item + 0x10, 'Q')
        print(json.dumps(result))
