"""Inspect only native party control fields for the dedicated companion."""
from pathlib import Path
import json
import struct
from wire import Reader

root = Path('/var/lib/ak-bots/arden')
notice = root / 'party-last-TeamInviteNotice.bin'
if notice.exists():
    data = Reader(notice.read_bytes())
    print(json.dumps(dict(inviter=data.number('I'), name=data.text(), fields=[data.number('h') for _ in range(3)])))
result = root / 'party-last-TeamInviteResult.bin'
if result.exists():
    # Ordinary control fields only; this payload contains no account/ticket data.
    print('result_length', result.stat().st_size, 'result_hex', result.read_bytes().hex())
