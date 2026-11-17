"""Apply the mall-debit hook to the live ZoneServer (python3.9 stdlib).

Appends the debit blobs + reason string + u32 price table to the executable
PT_LOAD that already hosts the mall-enhancement hook, extends filesz/memsz,
and retargets the two delivery-site jmps at the debit blobs.
Refuses to run twice and refuses to overwrite the backup.
"""
import hashlib, json, os, struct, sys

path = '/root/hxsy/ZoneServer/ZoneServer'
backup = '/root/hxsy/ZoneServer/ZoneServer.pre-mall-debit'
report_path = '/root/mall-debit-deployment.json'
code = open('/tmp/mall-debit-code.bin', 'rb').read()      # 512 bytes: blob1, blob2, reason
price = open('/tmp/mall-debit-price.bin', 'rb').read()    # 262144 bytes u32 table
assert len(code) == 0x210, len(code)
assert len(price) == 262144, len(price)

data = bytearray(open(path, 'rb').read())
orig_sha = hashlib.sha256(data).hexdigest()

phoff, phentsize, phnum = struct.unpack_from('<Q', data, 0x20)[0], struct.unpack_from('<H', data, 0x36)[0], struct.unpack_from('<H', data, 0x38)[0]
loads = []
for i in range(phnum):
    h = struct.unpack_from('<IIQQQQQQ', data, phoff + i * phentsize)
    if h[0] == 1:
        loads.append(h)
seg = [h for h in loads if h[3] == 0x16ba000]
assert len(seg) == 1, 'enhancement segment not found'
segidx = loads.index(seg[0])
t, flags, off, vaddr, paddr, filesz, memsz, align = seg[0]
assert flags == 5 and off == 0x1d980000 and filesz == memsz == 0x11000, \
    ('unexpected segment state', hex(flags), hex(off), hex(filesz), hex(memsz))
assert off + filesz == len(data), ('segment does not extend to EOF', off + filesz, len(data))

def vaddr_off(v):
    # map vaddr through the PT_LOADs (first is identity-mapped off=0 vaddr=0x400000)
    for t2, fl2, o2, va2, _, fs2, _, _ in loads:
        if va2 <= v < va2 + fs2:
            return o2 + v - va2
    raise AssertionError('vaddr not mapped', hex(v))

# pre-state assertions: original site jmps intact, enhancement entries present
assert bytes(data[vaddr_off(0x7c787f):vaddr_off(0x7c787f) + 6]) == bytes.fromhex('e9bc27ef0090'), 'site 1 already patched?'
assert bytes(data[vaddr_off(0x7c7f10):vaddr_off(0x7c7f10) + 6]) == bytes.fromhex('e98b22ef0090'), 'site 2 already patched?'
assert bytes(data[vaddr_off(0x16ba040):vaddr_off(0x16ba040) + 16]).hex() == '50515256574150415141524153415748', 'enhancement entry 1 missing'
assert bytes(data[vaddr_off(0x16ba1a0):vaddr_off(0x16ba1a0) + 16]).hex() == '50515256574150415141524153415748', 'enhancement entry 2 missing'

# backup under a fresh name (never overwrite a differing backup)
if os.path.exists(backup):
    existing = hashlib.sha256(open(backup, 'rb').read()).hexdigest()
    if existing != orig_sha:
        sys.exit('refusing: %s exists with different content' % backup)
    print('reusing existing identical backup:', backup)
else:
    open(backup, 'wb').write(bytes(data))

# append: blob region 0x16cb000..0x16d0000, then table 0x16d0000..0x1710000
base = len(data)  # == off + 0x11000 -> vaddr 0x16cb000
new_size = 0x56000
data.extend(b'\0' * (new_size - filesz))
assert len(data) == off + new_size
blob_vaddr = 0x16cb000
data[base:base + len(code)] = code
data[base + (0x16d0000 - blob_vaddr): base + (0x16d0000 - blob_vaddr) + len(price)] = price

# extend the segment
struct.pack_into('<QQ', data, phoff + segidx * phentsize + 32, new_size, new_size)

# retarget the site jmps
for site, target in ((0x7c787f, 0x16cb000), (0x7c7f10, 0x16cb100)):
    rel = target - (site + 5)
    assert -2 ** 31 <= rel < 2 ** 31
    data[vaddr_off(site):vaddr_off(site) + 6] = b'\xe9' + struct.pack('<i', rel) + b'\x90'

tmp = path + '.patching'
open(tmp, 'wb').write(bytes(data))
os.chmod(tmp, 0o750)
os.replace(tmp, path)   # rename works despite ETXTBSY on the running inode
report = dict(
    code_address=0x16cb000, code2_address=0x16cb100, reason_address=0x16cb200,
    table_address=0x16d0000, table_size=len(price),
    sites=[{'site': 0x7c787f, 'target': 0x16cb000}, {'site': 0x7c7f10, 'target': 0x16cb100}],
    segment_vaddr=0x16ba000, segment_old_size=0x11000, segment_new_size=new_size,
    file_size_before=len(data) - (new_size - filesz), original_sha256=orig_sha,
    patched_sha256=hashlib.sha256(bytes(data)).hexdigest(),
    backup=backup, validation='16 unicorn cases passed; live purchase test pending',
)
open(report_path, 'w').write(json.dumps(report, indent=2))
print('patched:', path, 'size', len(data), '(grew %d bytes)' % (new_size - filesz))
print('backup:', backup)
print(json.dumps({k: report[k] for k in ('code_address', 'table_address', 'segment_new_size', 'original_sha256', 'patched_sha256')}, indent=2))
