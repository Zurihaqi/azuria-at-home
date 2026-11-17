"""Unicorn verification of the damage-cap patch.

Emulates the four distinct clamp shapes from the patched scratch copy with
damage/HP values around the old cap (99,999,999) and the new cap (INT32_MAX):
  A. CCharFormula::Attack(CCharacter*,...) tail clamp
  B. CCharFormula::MaxHP(CCharacter*, bool) clamp
  C. CEudemonBattleFormula::GetMaxHP(CEBCharacter*) clamp (negative -> 0)
  D. CCoins::GetMaxValue(short) return
Exits non-zero on any mismatch. 21/21 byte-level round-trip was already
asserted by build-damage-cap-patch.py.
"""
import struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import *

P = r'D:\Games\Aura Kingdom Private Server\staging\ultimate\hxsy\ZoneServer\ZoneServer.damage-cap-test'
OLD_CAP = 0x5F5E0FF
NEW_CAP = 0x7FFFFFFF

f = open(P, 'rb')
f.seek(16)
vals = struct.unpack('<HHIQQQIHHHHHH', f.read(48))
e_shoff, e_shentsize, e_shnum, e_shstrndx = vals[5], vals[10], vals[11], vals[12]
f.seek(e_shoff)
shs = [struct.unpack('<IIQQQQIIQQ', f.read(e_shentsize)) for i in range(e_shnum)]
byname = {}
for h in shs:
    f.seek(shs[e_shstrndx][4] + h[0])
    byname[f.read(64).split(b'\0')[0].decode('latin1')] = h
text = byname['.text']
f.seek(text[4]); code = f.read(text[5])
base = text[3]

def run(start, end, regs, rip_end):
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    CODE = 0x400000
    uc.mem_map(CODE, 0x1000)
    blob = code[start - base:end - base]
    uc.mem_write(CODE + (start & 0xfff), blob)
    mapping = {UC_X86_REG_RAX: 'rax', UC_X86_REG_RBX: 'rbx', UC_X86_REG_RCX: 'rcx',
               UC_X86_REG_RDX: 'rdx', UC_X86_REG_RBP: 'rbp', UC_X86_REG_RSP: 'rsp'}
    rsp = 0x200000
    uc.mem_map(rsp, 0x10000)
    uc.reg_write(UC_X86_REG_RSP, rsp + 0x8000)
    for r, v in regs.items():
        uc.reg_write(r, v)
    uc.emu_start(CODE + (start & 0xfff), CODE + (rip_end & 0xfff))
    return uc.reg_read(UC_X86_REG_RAX), uc.reg_read(UC_X86_REG_RBP) & 0xffffffff

cases = []

# A. Attack(CCharacter) tail: xor edx,edx; test ebp,ebp; mov eax,cap;
#    cmovns edx,ebp; cmp edx,cap; cmovle eax,edx  ->  eax = clamp(ebp)
for v, want in [(-1, 0), (50_000_000, 50_000_000), (OLD_CAP, OLD_CAP),
                (100_000_000, 100_000_000), (NEW_CAP, NEW_CAP)]:
    cases.append(('Attack(CCharacter) clamp', 0x97eeee, 0x97ef03,
                  {UC_X86_REG_RBP: v & 0xffffffff}, 'rax', want))

# B. MaxHP clamp: cmp ebp,cap; jle 0x9890a0 — for signed int32 the jump is
#    always taken (nothing exceeds INT32_MAX signed), so only the taken path
#    is emulatable; the mov is a safety net. ebp must pass through unchanged.
for v in (50_000_000, OLD_CAP, NEW_CAP):
    cases.append(('MaxHP clamp (pass-through)', 0x989075, 0x9890a0,
                  {UC_X86_REG_RBP: v & 0xffffffff}, 'rbp', v))

# C. Eudemon GetMaxHP(CEBCharacter): mov eax,0; mov edx,ecx; cmovs edx,eax;
#    mov eax,cap; cmp edx,cap; cmovle eax,edx  ->  eax = max(0,min(ecx,cap))
#    (cmovs consumes SF set by the add before this window — seed it)
for v, want in [(-5, 0), (50_000_000, 50_000_000), (OLD_CAP, OLD_CAP),
                (100_000_000, 100_000_000), (NEW_CAP, NEW_CAP)]:
    cases.append(('Eudemon GetMaxHP(CEBCharacter)', 0xb81a41, 0xb81a59,
                  {UC_X86_REG_RCX: v & 0xffffffff,
                   UC_X86_REG_EFLAGS: (0x80 if v < 0 else 0)}, 'rax', want))

# D2. Eudemon shapes with a jump: cmp eax,cap; jg -> mov eax,cap tail is
#     unreachable for signed int32 (nothing exceeds INT32_MAX), so only the
#     not-taken path (test; mov edx,1; cmovle = min 1) is emulatable
for v, want, until in [(50_000_000, 50_000_000, 0xb80e0e),
                       (-5, 1, 0xb80e0e)]:
    cases.append(('Eudemon GetMaxHP(CEBEudemon)', 0xb80dfd, until,
                  {UC_X86_REG_RAX: v & 0xffffffff}, 'rax', want))
for v, want, until in [(50_000_000, 50_000_000, 0xb82f24),
                       (-5, 1, 0xb82f24)]:
    cases.append(('Eudemon GetMaxHP(CEBMonster)', 0xb82f12, until,
                  {UC_X86_REG_RAX: v & 0xffffffff}, 'rax', want))

# D. CCoins::GetMaxValue: mov eax,cap; ret
cases.append(('CCoins::GetMaxValue', 0x98da48, 0x98da4d, {}, 'rax', NEW_CAP))

fails = 0
for name, start, end, regs, which, want in cases:
    try:
        rax, rbp = run(start, end, regs, end)
    except Exception as e:
        print('%-32s EMU ERROR: %s' % (name, e))
        fails += 1
        continue
    got = {'rax': rax & 0xffffffff, 'rbp': rbp}[which]
    ok = got == want
    if not ok:
        fails += 1
    print('%-32s got %-12s want %-12s %s' % (name, got, want, 'OK' if ok else 'FAIL'))

print()
print('passed %d/%d' % (len(cases) - fails, len(cases)))
sys.exit(1 if fails else 0)
