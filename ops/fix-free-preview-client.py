"""Allow zero-price voucher offers in the native fitting-room UI.

The item-ID check and negative-price rejection remain intact. No AP path changes.
Run only after the client has exited. A complete executable backup is retained.
"""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import struct
import sys
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EBX, UC_X86_REG_EIP

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / 'client/Requiem Aurakingdom/game.bin'
data = bytearray(path.read_bytes())
pe = pefile.PE(data=bytes(data))
address = 0xd500cd
offset = pe.get_offset_from_rva(address - pe.OPTIONAL_HEADER.ImageBase)
before = bytes.fromhex('0f8e23020000')  # price <= 0 -> unavailable
after = bytes.fromhex('0f8c23020000')   # price < 0 -> unavailable
assert data[offset:offset + 6] == before, 'Client build or patch state changed'
data[offset:offset + 6] = after

# Execute the actual item-ID / price guard from this executable for both builds.
def guard(code, item, price):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    uc.mem_map(0xd50000, 0x1000)
    uc.mem_map(0x100000, 0x1000)
    start = pe.get_offset_from_rva(0xd500bf - pe.OPTIONAL_HEADER.ImageBase)
    native = bytearray(data[start:start + 20])
    native[address - 0xd500bf:address - 0xd500bf + 6] = code
    uc.mem_write(0xd500bf, bytes(native))
    uc.mem_write(0x100000, struct.pack('<H', item))
    uc.mem_write(0x100010, struct.pack('<i', price))
    uc.reg_write(UC_X86_REG_EBX, 0x100000)
    result = []
    def stop(vm, addr, size, extra):
        if addr in (0xd500d3, 0xd502f6):
            result.append('available' if addr == 0xd500d3 else 'unavailable')
            vm.emu_stop()
    uc.hook_add(UC_HOOK_CODE, stop)
    uc.emu_start(0xd500bf, 0xd502f7, count=20)
    assert len(result) == 1
    return result[0]

tests = []
for item, price, expected in ((51974, 0, 'available'), (53460, 0, 'available'),
                              (51974, 22, 'available'), (51974, -1, 'unavailable'),
                              (51974, -2147483648, 'unavailable'),
                              (51974, 2147483647, 'available'),
                              (0, 0, 'unavailable'), (0, 22, 'unavailable')):
    actual = guard(after, item, price)
    assert actual == expected, (item, price, actual, expected)
    tests.append(dict(item=item, price=price, result=actual))
assert guard(before, 51974, 0) == 'unavailable'
assert guard(before, 51974, 22) == 'available'

stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = ROOT / 'private/client-original' / ('free-preview-' + stamp)
backup.mkdir(parents=True)
shutil.copy2(path, backup / path.name)
old_hash = hashlib.sha256(path.read_bytes()).hexdigest()
with path.open('r+b') as stream:
    stream.seek(offset)
    assert stream.read(6) == before
    stream.seek(offset)
    stream.write(after)
new = path.read_bytes()
assert new == data
report = dict(address=hex(address), offset=offset, before=before.hex(),
              after=after.hex(), backup=str(backup), tests=tests,
              before_sha256=old_hash, after_sha256=hashlib.sha256(new).hexdigest())
(ROOT / 'docs/free-preview-client-report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
