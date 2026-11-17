"""Emulate the mall-debit chain: debit blob -> existing enhancement blob -> site+6.

GainCoins is stubbed and its arguments captured; the enhancement's server APIs are
stubbed like the original verifier. Checks amount arithmetic, wallet routing,
stack ABI, register/stack balance, and skip paths.
"""
from pathlib import Path
import json, struct, sys
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.x86_const import *

root = Path(__file__).resolve().parent.parent
manifest = json.loads((root / 'docs/mall-debit-hook.json').read_text())
enh = json.loads((root / 'docs/mall-enhancement-hook.json').read_text())
code = (root / 'ops/mall-debit-code.bin').read_bytes()
price = (root / 'ops/mall-debit-price.bin').read_bytes()
enhcode = (root / 'ops/mall-enhancement-code.bin').read_bytes()
enhmask = (root / 'ops/mall-enhancement-mask.bin').read_bytes()

def table_price(iid):
    return struct.unpack_from('<I', price, iid * 4)[0]

GOLD_ID = 10001                  # mu=1, point 12 (live DB verified)
assert table_price(GOLD_ID) == 12
cat = json.loads((root / 'docs/mall-f2p-catalog.json').read_text())['items']
BIND_ID = next((x['id'] for x in cat if x['money_unit'] == 2), None)
assert BIND_ID is not None and table_price(BIND_ID) == 0
BIG_PRICE_ID = max(range(65536), key=lambda i: struct.unpack_from('<I', price, i * 4)[0])
assert table_price(BIG_PRICE_ID) == 6240

REASON = manifest['reason_address']
GAINCOINS = manifest['gaincoins']
API = {GAINCOINS: 'gaincoins', 0x4b2c20: 'fortify', 0x4a9da0: 'attrs', 0x8a2620: 'persist_stars',
       0x88dc10: 'flush', 0xdf0a40: 'allocate', 0x609650: 'notify'}

cases = 0
for hook in manifest['sites']:
    site, site6 = hook['site'], hook['site'] + 6
    scenarios = [
        # (name, item(rax or None), event_id, qty, group, expect_debit)
        ('gold x3', 'item', GOLD_ID, 3, 1, -36000),
        ('qty0 clamps to 1', 'item', GOLD_ID, 0, 1, -12000),
        ('bind-gold row skipped', 'item', BIND_ID, 1, 1, None),
        ('unknown item skipped', 'item', 49999, 5, 1, None),
        ('delivery-failure skipped', None, GOLD_ID, 3, 1, None),
        ('over-2M skipped', 'item', BIG_PRICE_ID, 400, 1, None),
        ('2M boundary debits', 'item', BIG_PRICE_ID, 320, 1, -1996800000),
        ('coexists with enhancement', 'item', GOLD_ID, 3, 6, -36000),
    ]
    for name, itemmode, ev_id, qty, group, expect in scenarios:
        u = Uc(UC_ARCH_X86, UC_MODE_64)
        u.mem_map(0x400000, 0x1310000)     # covers .text stubs, blob region, table, through 0x1710000
        u.mem_map(0x2000000, 0x20000)
        u.mem_write(manifest['code_address'], code)
        u.mem_write(manifest['table_address'], price)
        u.mem_write(enh['code_address'], enhcode)
        u.mem_write(enh['table_address'], enhmask)
        stack = 0x2010000; item = 0x2001000; template = 0x2002000; event = 0x2003000
        char = 0x2004000; container = 0x2007000; db = 0x2008000; packet = 0x2009000
        item_v = 0 if itemmode is None else item
        u.mem_write(item + 16, struct.pack('<Q', template)); u.mem_write(template + 8, struct.pack('<H', ev_id))
        u.mem_write(item + 64, struct.pack('<H', 3))
        u.mem_write(event + 0x24, struct.pack('<H', ev_id))
        u.mem_write(event + 0x26, struct.pack('<H', qty))
        u.mem_write(event + 0x34, struct.pack('<H', group))
        u.mem_write(char + 0x38, struct.pack('<I', 50000001))
        u.mem_write(stack + 0x40, struct.pack('<H', 12)); u.mem_write(stack + 0x90, struct.pack('<H', 12))
        # synthetic mask bits for the coexistence case (test id is not real gear)
        u.mem_write(enh['table_address'] + ev_id, bytes([3]))
        for addr, value in [(0x16807f0, 0x200a000), (0x16902a0, db), (db + 0x40, 0x200b000), (db + 0x18, 0x200c000)]:
            u.mem_write(addr, struct.pack('<Q', value))
        entry_rsp = stack
        regs = {UC_X86_REG_RAX: item_v, UC_X86_REG_RBX: event, UC_X86_REG_R12: char, UC_X86_REG_R13: 2,
                UC_X86_REG_R14: container, UC_X86_REG_R15: 0x12345678, UC_X86_REG_RSP: entry_rsp,
                UC_X86_REG_RCX: 11, UC_X86_REG_RDX: 22, UC_X86_REG_RSI: 33, UC_X86_REG_RDI: 44,
                UC_X86_REG_R8: 55, UC_X86_REG_R9: 66, UC_X86_REG_R10: 77, UC_X86_REG_R11: 88}
        for reg, value in regs.items():
            u.reg_write(reg, value)
        calls = []
        def intercept(uc, address, size, data):
            if address == site6:
                uc.emu_stop(); return
            if address not in API:
                return
            sp = uc.reg_read(UC_X86_REG_RSP)
            name = API[address]
            calls.append((name, sp))
            if name == 'gaincoins':
                assert sp % 16 == 8, ('misaligned GainCoins call', hex(sp))
                args = dict(rdi=uc.reg_read(UC_X86_REG_RDI), esi=uc.reg_read(UC_X86_REG_RSI),
                            edx=uc.reg_read(UC_X86_REG_EDX) - (1 << 32) if uc.reg_read(UC_X86_REG_EDX) >= 1 << 31 else uc.reg_read(UC_X86_REG_EDX), ecx=uc.reg_read(UC_X86_REG_RCX),
                            r8d=uc.reg_read(UC_X86_REG_R8D), r9d=uc.reg_read(UC_X86_REG_R9D),
                            a7=struct.unpack('<I', uc.mem_read(sp + 8, 4))[0],
                            a8=struct.unpack('<I', uc.mem_read(sp + 0x10, 4))[0],
                            a9=struct.unpack('<I', uc.mem_read(sp + 0x18, 4))[0],
                            a10=struct.unpack('<I', uc.mem_read(sp + 0x20, 4))[0],
                            a11=uc.mem_read(sp + 0x28, 1)[0])
                assert args == dict(rdi=char, esi=1, edx=expect, ecx=REASON, r8d=0, r9d=1,
                                    a7=0, a8=0, a9=14, a10=95, a11=0), (name, args, 'expect', expect)
            else:
                assert sp % 16 == 8, ('misaligned api call', name, hex(sp))
            ret = struct.unpack('<Q', uc.mem_read(sp, 8))[0]
            for r in [UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_RSI, UC_X86_REG_RDI,
                      UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_R10, UC_X86_REG_R11]:
                uc.reg_write(r, 0xabcdef)
            uc.reg_write(UC_X86_REG_RAX, packet if name == 'allocate' else 1 if name == 'gaincoins' else 0)
            uc.reg_write(UC_X86_REG_RSP, sp + 8); uc.reg_write(UC_X86_REG_RIP, ret)
        u.hook_add(UC_HOOK_CODE, intercept)
        def invalid(uc, access, address, size, value, data):
            print('Invalid access', hex(address), 'rip', hex(uc.reg_read(UC_X86_REG_RIP)), 'calls', calls)
            return False
        u.hook_add(UC_HOOK_MEM_INVALID, invalid)
        u.emu_start(hook['target'], site6, count=200000)
        for reg, value in regs.items():
            assert u.reg_read(reg) == value, (name, 'reg', hex(reg), u.reg_read(reg), value)
        assert u.reg_read(UC_X86_REG_RBP) == item_v, (name, 'rbp')
        gcalls = [c for c in calls if c[0] == 'gaincoins']
        assert len(gcalls) == (1 if expect is not None else 0), (name, 'gaincoins call count', len(gcalls))
        cases += 1
    print(f'site {site:#x}: {len(scenarios)} scenarios OK')
print(f'Passed {cases} emulated debit cases across {len(manifest["sites"])} hook sites: '
      f'amount arithmetic, wallet routing, stack ABI, register/stack balance, skip paths, enhancement coexistence.')
