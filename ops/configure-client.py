from pathlib import Path
import hashlib
import ipaddress
import json
import re
import sys

root = Path(__file__).resolve().parent.parent
server = str(ipaddress.IPv4Address(sys.argv[1]))
client = root / 'client/Requiem Aurakingdom'
backup = root / 'private/client-original'
backup.mkdir(exist_ok=True)
changes = []
for name in ('connect.ini', 'connects.ini'):
    target = client / name
    original = target.read_bytes()
    saved = backup / name
    if not saved.exists():
        saved.write_bytes(original)
    if name == 'connect.ini':
        updated = f'Server={server},6543\r\n'.encode('ascii')
    else:
        first = original.splitlines()[0]
        updated = re.sub(rb'=.*$', ('=' + server + ',6543').encode('ascii'), first) + b'\r\n'
    # Windows rejects O_CREAT on some hidden files; preserve its attributes.
    with target.open('r+b') as output:
        output.write(updated)
        output.truncate()
    changes.append({'file': name, 'sha256': hashlib.sha256(updated).hexdigest()})
(root / 'docs/client-connection.json').write_text(json.dumps({'server': server, 'login_port': 6543, 'files': changes}, indent=2))
print('Client connection configured; original bytes preserved in private/client-original')
