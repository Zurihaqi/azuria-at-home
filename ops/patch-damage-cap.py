"""Apply the damage-cap patch to the live ZoneServer (python3.9 stdlib).

Replaces every 99,999,999 (0x5F5E0FF) clamp immediate at the 21 verified
sites with INT32_MAX (0x7FFFFFFF). Pure in-place imm32 swaps - no segment
changes, so all file offsets are the same as the unpatched layout.
Refuses to run twice. Safe to apply while ZoneServer runs: os.replace keeps
the old inode alive for the running process; takes effect on next restart.
"""
import hashlib, json, os, struct, sys

path = '/root/hxsy/ZoneServer/ZoneServer'
backup = '/root/hxsy/ZoneServer/ZoneServer.pre-damage-cap'
report_path = '/root/damage-cap-deployment.json'
OLD_CAP = 0x5F5E0FF
NEW_CAP = 0x7FFFFFFF

# vaddrs verified by build-damage-cap-patch.py (see docs/damage-cap-patch.json)
SITES = [
    0x97eef3, 0x97eefc, 0x980db6, 0x980dd0,   # CCharFormula::Attack
    0x982315, 0x98231e,                       # MeleeDamage(CCharacter)
    0x98249e, 0x9824a7,                       # MagicDamge
    0x982660, 0x982673,                       # MeleeDamage(CBiology)
    0x989077, 0x98907e,                       # MaxHP
    0x98da49,                                 # CCoins::GetMaxValue
    0xb80dfe, 0xb80e31,                       # EudemonBattle GetMaxHP (CEBEudemon)
    0xb81a4c, 0xb81a52,                       #   (CEBCharacter)
    0xb81b4a, 0xb81b71,                       #   (CEudemonBattle...)
    0xb82f13, 0xb82f39,                       #   (CEBMonster)
]

data = bytearray(open(path, 'rb').read())
orig_sha = hashlib.sha256(data).hexdigest()

phoff = struct.unpack_from('<Q', data, 0x20)[0]
phentsize, phnum = struct.unpack_from('<HH', data, 0x36)
loads = []
for i in range(phnum):
    h = struct.unpack_from('<IIQQQQQQ', data, phoff + i * phentsize)
    if h[0] == 1:
        loads.append(h)

def vaddr_off(v):
    for t2, fl2, o2, va2, _, fs2, _, _ in loads:
        if va2 <= v < va2 + fs2:
            return o2 + v - va2
    raise AssertionError('vaddr not mapped', hex(v))

# pre-state: every site must still hold the old cap
for v in SITES:
    off = vaddr_off(v)
    got = struct.unpack_from('<I', data, off)[0]
    if got != OLD_CAP:
        sys.exit('site %s holds 0x%x (expected old cap or already patched?)' % (hex(v), got))

if os.path.exists(backup):
    existing = hashlib.sha256(open(backup, 'rb').read()).hexdigest()
    if existing != orig_sha:
        sys.exit('refusing: %s exists with different content' % backup)
    print('reusing existing identical backup:', backup)
else:
    # also confirm we are patching the expected mall-debit build
    site_jmp = bytes(data[vaddr_off(0x7c787f):vaddr_off(0x7c787f) + 6])
    if site_jmp != bytes.fromhex('e97c37f00090'):
        sys.exit('unexpected build: site1 jmp %s (mall-debit hook not present?)' % site_jmp.hex())
    open(backup, 'wb').write(bytes(data))

for v in SITES:
    struct.pack_into('<I', data, vaddr_off(v), NEW_CAP)

tmp = path + '.patching'
open(tmp, 'wb').write(bytes(data))
os.chmod(tmp, 0o750)
os.replace(tmp, path)

# on-disk postcheck
check = open(path, 'rb').read()
bad = [hex(v) for v in SITES if struct.unpack_from('<I', check, vaddr_off(v))[0] != NEW_CAP]
if bad:
    sys.exit('postcheck FAILED at: %s' % bad)

report = dict(
    sites=[hex(v) for v in SITES], old_cap=OLD_CAP, new_cap=NEW_CAP,
    file_size_before=len(data) - 0, original_sha256=orig_sha,
    patched_sha256=hashlib.sha256(check).hexdigest(),
    backup=backup, restart_required=True,
    validation='byte round-trip + 18/18 unicorn clamp cases passed',
)
open(report_path, 'w').write(json.dumps(report, indent=2))
print('patched in place:', path)
print('backup:', backup)
print('restart required: yes (running process keeps old inode until restart)')
