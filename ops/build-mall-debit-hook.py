"""Build the ZoneServer mall-debit hook: gold-debit blobs + u32 unit-price table.

Chain: site (jmp) -> debit blob -> enhancement-hook entry (existing) -> site+6.
Debit = CCharacter::GainCoins(char, 1, -(price*qty*1000), "ItemMall", 0, 1, 0, 0, 14, 95, 0)
with the exact constants the native SpecialItemmallReqBuy debit uses.
Only money_unit=1 rows get a table entry; money_unit=2 (bind gold) is DB-authoritative
in this build (CCharacter+0x2718 has no memory reader/writer, GainBindGold is a stub,
no save fieldlist contains bind_gold) so those rows table as 0 = no debit.
"""
from pathlib import Path
import csv, json, os, sys
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
from keystone import Ks, KS_ARCH_X86, KS_MODE_64

root = Path(__file__).resolve().parent.parent
BLOB1 = 0x16cb000
BLOB2 = 0x16cb100
REASON = 0x16cb200
TABLE = 0x16d0000
TABLE_END = 0x1710000          # 0x16ba000 + 0x56000
SEGMENT_VADDR = 0x16ba000
SEGMENT_NEW_SIZE = TABLE_END - SEGMENT_VADDR   # 0x56000
GAINCOINS = 0xa000f0
SITES = [0x7c787f, 0x7c7f10]   # inside CNE_ZW_ZoneServerItemMallReceieveAttempt::Execute
ENTRIES = [0x16ba040, 0x16ba1a0]  # existing mall-enhancement-hook blob entries

# --- price table from the catalog (cross-checked against optional live CSV dump) ---
table = {}
cat = json.loads((root / 'docs/mall-f2p-catalog.json').read_text())['items']
catm = {x['id']: (x['money_unit'], x['price']) for x in cat}
live = dict(catm)
csv_path = Path(os.environ.get('ITEMMALL_LIVE_CSV', root / 'private/itemmall-live.csv'))
if csv_path.is_file():
    live = {}
    for line in csv_path.read_text(encoding='utf-8', newline='').splitlines():
        line = line.strip()
        if not line or 'could not change directory' in line:
            continue
        iid, mu, point, num = line.split(',')
        iid = int(iid); mu = int(mu); point = int(point)
        assert iid not in live, ('duplicate item id in DB', iid)
        assert 0 < iid < 65536, ('item id out of table range', iid)
        assert point >= 1, ('zero/negative point', iid, point)
        assert point <= 10000, ('unit price above cap', iid, point)
        live[iid] = (mu, point)
assert set(live) == set(catm), 'live DB and catalog item sets differ'
assert all(live[i] == catm[i] for i in live), 'live DB and catalog prices differ'

mask = bytearray(4 * 65536)
gold_rows = 0
for iid, (mu, point) in live.items():
    if mu == 1:
        struct_off = iid * 4
        mask[struct_off:struct_off + 4] = point.to_bytes(4, 'little')
        gold_rows += 1
# no table collision with the special-branch ids the delivery path treats specially
for special in (0x9ef0, 0x9d59, 0x9f58):
    assert live.get(special, (2, 0))[0] != 1, 'special-branch id priced in gold'

ASSEMBLY = f'''
test rax,rax
jz done
push rax
push rcx
push rdx
push rsi
push rdi
push r8
push r9
push r10
push r11
sub rsp,0x28
movzx r10d,word ptr [rbx+0x26]
test r10d,r10d
jg haveq
mov r10d,1
haveq:
movzx r11d,word ptr [rbx+0x24]
shl r11d,2
mov r11d,dword ptr [r11+{TABLE:#x}]
test r11d,r11d
jz skip
imul r11d,r10d
cmp r11d,2000000
ja skip
imul r11d,1000
neg r11d
mov qword ptr [rsp],0
mov qword ptr [rsp+8],0
mov dword ptr [rsp+0x10],0xe
mov dword ptr [rsp+0x18],0x5f
mov byte ptr [rsp+0x20],0
mov rdi,r12
mov esi,1
mov edx,r11d
mov ecx,{REASON:#x}
mov r8d,0
mov r9d,1
call {GAINCOINS:#x}
skip:
add rsp,0x28
pop r11
pop r10
pop r9
pop r8
pop rdi
pop rsi
pop rdx
pop rcx
pop rax
done:
jmp %s
'''

blobs = []
ks = Ks(KS_ARCH_X86, KS_MODE_64)
for blob_addr, entry in zip([BLOB1, BLOB2], ENTRIES):
    asm = ASSEMBLY % f'{entry:#x}'
    encoded, count = ks.asm(asm, addr=blob_addr)
    encoded = bytes(encoded)
    assert len(encoded) < 0x100, 'blob overflows its slot'
    blobs.append(encoded)

code = bytearray(0x210)
code[0:len(blobs[0])] = blobs[0]
code[0x100:0x100 + len(blobs[1])] = blobs[1]
reason = b'ItemMall\x00'
code[REASON - BLOB1:REASON - BLOB1 + len(reason)] = reason

(root / 'ops/mall-debit-code.bin').write_bytes(bytes(code))
(root / 'ops/mall-debit-price.bin').write_bytes(bytes(mask))

# quick static sanity: disassemble both blobs with capstone and confirm the terminal jmp
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
md = Cs(CS_ARCH_X86, CS_MODE_64)
for i, (blob_addr, entry) in enumerate(zip([BLOB1, BLOB2], ENTRIES)):
    blob = blobs[i]
    *_, last = md.disasm(blob, blob_addr)
    assert last.mnemonic == 'jmp' and last.op_str == f'{entry:#x}', (i, last.mnemonic, last.op_str)
    print(f'blob{i + 1} @ {blob_addr:#x}: {len(blob)} bytes, terminal jmp -> {entry:#x}')

manifest = {
    'code_address': BLOB1, 'code2_address': BLOB2, 'reason_address': REASON,
    'reason': 'ItemMall', 'table_address': TABLE, 'table_size': 4 * 65536,
    'segment_vaddr': SEGMENT_VADDR, 'segment_new_size': SEGMENT_NEW_SIZE,
    'sites': [{'site': s, 'entry': e, 'target': t} for s, e, t in zip(SITES, ENTRIES, [BLOB1, BLOB2])],
    'gaincoins': GAINCOINS,
    'gold_rows': gold_rows, 'bind_rows': len(live) - gold_rows,
    'amount_rule': 'unit price x quantity x 1000 base units, negative debit, skipped if price=0 or total>2,000,000',
}
(root / 'docs/mall-debit-hook.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
