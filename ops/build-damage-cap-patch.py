"""Build the damage-cap patch for ZoneServer.

Raises the combat damage/HP wall from 99,999,999 (0x5F5E0FF) to INT32_MAX
(0x7FFFFFFF) at every genuine clamp site, excluding:
  - CPlayerFactory::FamilyInstanceCreate (unrelated threshold check)
  - CArcheologyOp/CFishingOp SetSectionDatas (pair with hard-coded 0x5F5E100
    arithmetic that would desync)

Writes:
  - a patched scratch copy of the staging binary for verification
  - docs/damage-cap-patch.json manifest (file offsets valid for the deployed
    binary too: the mall-debit deployment only appended a segment, the
    .text file offsets are unchanged)
Run locally. Deployment is ops/patch-damage-cap.py on the VM.
"""
import hashlib, json, os, shutil, struct, datetime
import capstone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'staging', 'ultimate', 'hxsy', 'ZoneServer', 'ZoneServer')
OUT = os.path.join(ROOT, 'staging', 'ultimate', 'hxsy', 'ZoneServer', 'ZoneServer.damage-cap-test')
MANIFEST = os.path.join(ROOT, 'docs', 'damage-cap-patch.json')

OLD_CAP = 0x5F5E0FF
NEW_CAP = 0x7FFFFFFF

# vaddr of the imm32 operand for every site to patch
SITES = [
    # CCharFormula::Attack(CCharacter*, float, bool) tail clamp
    0x97eef3, 0x97eefc,
    # CCharFormula::Attack(CBiology*, bool)
    0x980db6, 0x980dd0,
    # CCharFormula::MeleeDamage(CCharacter*, short, bool)
    0x982315, 0x98231e,
    # CCharFormula::MagicDamge(...)
    0x98249e, 0x9824a7,
    # CCharFormula::MeleeDamage(CBiology*, bool)
    0x982660, 0x982673,
    # CCharFormula::MaxHP(CCharacter*, bool)
    0x989077, 0x98907e,
    # CCoins::GetMaxValue(short)
    0x98da49,
    # CEudemonBattleFormula::GetMaxHP(CEBEudemon*)
    0xb80dfe, 0xb80e31,
    # ... (CEBCharacter*)
    0xb81a4c, 0xb81a52,
    # ... (CEudemonBattle...)
    0xb81b4a, 0xb81b71,
    # ... (CEBMonster*)
    0xb82f13, 0xb82f39,
]

data = bytearray(open(SRC, 'rb').read())
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

# --- verify each site: the imm must sit inside a decoded instruction that
# uses it as an operand, and the instruction stream must survive the swap.
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.skipdata = True

# minimal symbol table for function-start attribution
f = open(SRC, 'rb')
# layout: e_shoff@0x28, e_shentsize@0x3a, e_shnum@0x3c, e_shstrndx@0x3e
f.seek(0x28)
e_shoff, = struct.unpack('<Q', f.read(8))
f.seek(0x3a)
e_shentsize, e_shnum, e_shstrndx = struct.unpack('<HHH', f.read(6))
f.seek(e_shoff)
shs = [struct.unpack('<IIQQQQIIQQ', f.read(e_shentsize)) for _ in range(e_shnum)]
byname = {}
for h in shs:
    f.seek(shs[e_shstrndx][4] + h[0])
    byname[f.read(64).split(b'\0')[0].decode('latin1')] = h
text = byname['.text']
text_base, text_size = text[3], text[5]
h = byname['.symtab']; f.seek(h[4]); symtab = f.read(h[5])
h = byname['.strtab']; f.seek(h[4]); strtab = f.read(h[5])
funcs = []
for i in range(len(symtab) // 24):
    st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from('<IBBHQQ', symtab, i * 24)
    if (st_info & 0xf) != 2 or not st_size:
        continue
    end = strtab.find(b'\0', st_name)
    funcs.append((st_value, st_size, strtab[st_name:end].decode('latin1')))
funcs.sort()
starts = [a for a, s, n in funcs]

def fn_of(addr):
    i = bisect.bisect_right(starts, addr) - 1
    if i >= 0:
        a, s, n = funcs[i]
        if addr < a + s:
            return a, n
    raise AssertionError('no function for', hex(addr))

import bisect

entries = []
for v in SITES:
    off = vaddr_off(v)
    old = struct.unpack_from('<I', data, off)[0]
    assert old == OLD_CAP, ('site does not contain the cap', hex(v), hex(old))
    # decode the covering instruction by linear disasm from the function start
    fs, fname = fn_of(v)
    o0 = max(v - 0x60, fs)
    covering = None
    for ins in md.disasm(bytes(data)[vaddr_off(o0):off + 16], o0):
        if ins.address <= v < ins.address + ins.size:
            covering = ins
            break
        if ins.address > v:
            break
    assert covering is not None, ('imm not inside any instruction', hex(v))
    assert ('%#x' % OLD_CAP) in covering.op_str, ('imm not an operand', hex(v), covering.mnemonic, covering.op_str)
    entries.append(dict(vaddr=v, file_offset=off, function=fname,
                        insn='%s %s' % (covering.mnemonic, covering.op_str)))

# --- patch the scratch copy
for e in entries:
    struct.pack_into('<I', data, e['file_offset'], NEW_CAP)
open(OUT, 'wb').write(bytes(data))
patched_sha = hashlib.sha256(bytes(data)).hexdigest()

# --- round-trip verify: same instructions, only the immediate differs
data2 = open(OUT, 'rb').read()
for e in entries:
    off = e['file_offset']
    v = e['vaddr']
    fs, fname = fn_of(v)
    o0 = max(v - 0x60, fs)
    for ins in md.disasm(data2[vaddr_off(o0):off + 16], o0):
        if ins.address <= v < ins.address + ins.size:
            got = '%s %s' % (ins.mnemonic, ins.op_str)
            want = e['insn'].replace('0x5f5e0ff', '0x7fffffff')
            assert got == want, ('round-trip mismatch', hex(v), got, want)
            break

# --- confirm nothing else changed
a = open(SRC, 'rb').read()
# every diff byte must sit inside a site's imm32, and low byte is shared (0xff)
diffs = [i for i in range(len(a)) if a[i] != data2[i]]
assert all(any(e['file_offset'] <= d < e['file_offset'] + 4 for e in entries) for d in diffs), \
    'unexpected byte diffs outside sites'
assert len(diffs) == 3 * len(entries), ('diff byte count', len(diffs))

manifest = dict(
    built=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
    old_cap=OLD_CAP, new_cap=NEW_CAP,
    sites=entries,
    source_sha256=orig_sha, patched_sha256=patched_sha,
    excluded=[
        {'vaddr': 0x582860, 'function': 'CPlayerFactory::FamilyInstanceCreate', 'reason': 'unrelated threshold check'},
        {'vaddr': 0xb9c0cb, 'function': 'CArcheologyOp::SetSectionDatas', 'reason': 'pairs with 0x5F5E100 arithmetic'},
        {'vaddr': 0xba3ddb, 'function': 'CFishingOp::SetSectionDatas', 'reason': 'pairs with 0x5F5E100 arithmetic'},
        {'vaddr': 0xba4123, 'function': 'CFishingOp::SetSectionDatas', 'reason': 'pairs with 0x5F5E100 arithmetic'},
    ],
)
open(MANIFEST, 'w').write(json.dumps(manifest, indent=2))
print('sites patched:', len(entries))
print('scratch copy:', OUT)
print('manifest:', MANIFEST)
