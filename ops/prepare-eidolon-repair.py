"""Rebuild missing link drop entries and validate a zero-fragment skill charge."""
from pathlib import Path
import hashlib, json, struct, sys
sys.path.insert(0, str(Path(__file__).parent/'runtime'))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'staging/eidolon-repair';OUT.mkdir(exist_ok=True)
def table(path):
    raw=path.read_bytes();f=raw.decode('cp950',errors='surrogateescape').split('|');n=int(f[2])
    rows={int(r[0].strip()):r for i in range(3,len(f)-n,n) if (r:=f[i:i+n])[0].strip().isdigit()}
    return raw,n,rows
_,_,partners=table(ROOT/'staging/live-S_Partner.ini')
before,n,drops=table(ROOT/'staging/live-S_DropItem.ini')
items={}
for name in ('S_Item.ini','S_ItemMall.ini'):
    items.update(table(ROOT/'staging'/('eidolon-'+name))[2])
added=[];payload=before
for pid,p in partners.items():
    for gift in sorted({int(v) for v in p[81:91] if v and int(v) not in drops}):
        # Current release omitted these records. Reuse the last valid native
        # link distribution, substituting this partner's existing key fragment.
        r=drops[10113 if p[39] else 10096].copy();r[0]=str(gift);r[1]=p[4]
        key=int(p[39] or 0)
        fragment=key+1 if key else int(p[37])
        missing_fragment=fragment not in items
        if missing_fragment:fragment=11179  # Existing Hero Emblem; no invented template.
        assert fragment in items,(pid,key)
        if key and not missing_fragment:assert '碎片' in items[fragment][7] or 'frag' in items[fragment][7].lower(),(pid,fragment)
        r[9]=str(fragment);r[10]=items[fragment][7]
        # Generic native Eidolon card pack instead of guessing unverified IDs.
        r[25]='15325';r[26]=items[15325][7]
        statues=[i for i,v in items.items() if v[7]=='源神雕像．'+p[4] or v[7]=='源神雕像‧'+p[4]]
        statue=statues[0] if len(statues)==1 else 11047
        r[29]=str(statue);r[30]=items[statue][7]
        for col in (*range(9,129,4),*range(129,149,4)):
            if r[col]:assert int(r[col]) in items,(gift,col,r[col])
        assert sum(float(r[i] or 0) for i in range(12,129,4))==100
        payload+=(b'' if payload.endswith(b'\n') else b'\r\n')+('|'.join(r)+'|\r\n').encode('cp950',errors='surrogateescape')
        drops[gift]=r
        added.append(dict(partner=pid,gift=gift,fragment=fragment,statue=statue,missing_fragment_fallback=missing_fragment))
assert len(added)==37
(OUT/'S_DropItem.ini').write_bytes(payload)
assert len(table(OUT/'S_DropItem.ini')[2])==len(table(ROOT/'staging/live-S_DropItem.ini')[2])+37
assert all(int(v) in drops for p in partners.values() for v in p[81:91] if v)

binary=ROOT/'staging/eidolon-ZoneServer'
with binary.open('rb') as f:
    h=f.read(64);phoff=struct.unpack_from('<Q',h,32)[0];psz,pnum=struct.unpack_from('<HH',h,54)
    f.seek(phoff);ph=f.read(psz*pnum)
    loads=[struct.unpack_from('<IIQQQQQQ',ph,i*psz) for i in range(pnum) if struct.unpack_from('<I',ph,i*psz)[0]==1]
    def read(a,n):
        s=next(s for s in loads if s[3]<=a<a+n<=s[3]+s[5]);off=s[2]+a-s[3];f.seek(off);return off,f.read(n)
    offset,old=read(0x497753,7)
    assert old==bytes.fromhex('0fbf936a010000')
    new=bytes.fromhex('31d29090909090')
    _,native=read(0x4975f0,423)
patched=bytearray(native);patched[0x497753-0x4975f0:0x49775a-0x4975f0]=new

def check(current,slot,balance,cap=50):
    vm=Uc(UC_ARCH_X86,UC_MODE_64)
    vm.mem_map(0x400000,0x100000);vm.mem_map(0x100000,0x200000);vm.mem_map(0x1692000,0x6000)
    vm.mem_write(0x4975f0,bytes(patched))
    def w(a,v):vm.mem_write(a,struct.pack('<Q',v))
    # GameData singleton / vtable; ordinary partner and level lookups.
    w(0x1696ae0,0x110000);w(0x110000,0x120000)
    w(0x1692630,0x1b0000)
    for disp,addr in ((0x430,0x410000),(0x4f0,0x410010),(0x268,0x410020)):w(0x120000+disp,addr);vm.mem_write(addr,b'\xc3')
    vm.mem_write(0x496860,b'\xc3')
    w(0x140060,0x150000)
    if 0<=slot<3:
        w(0x150000+slot*24,0x160000);w(0x150008+slot*24,0x160018)
        vm.mem_write(0x13013a+slot*2,struct.pack('<h',current))
    vm.mem_write(0x17016a,struct.pack('<h',350))
    stack=0x2f0000;w(stack,0x410100)
    for reg,val in ((UC_X86_REG_RDI,0x180000),(UC_X86_REG_RSI,0x190000),(UC_X86_REG_RDX,0x130000),(UC_X86_REG_RCX,slot),(UC_X86_REG_R8,0x1a0000),(UC_X86_REG_RSP,stack)):vm.reg_write(reg,val)
    def hook(u,a,size,data):
        if a==0x410000:u.reg_write(UC_X86_REG_RAX,0x140000)
        elif a==0x410010:u.reg_write(UC_X86_REG_RAX,cap)
        elif a==0x410020:u.reg_write(UC_X86_REG_RAX,0x170000)
        elif a==0x496860:u.reg_write(UC_X86_REG_RAX,balance)
        elif a==0x410100:u.emu_stop()
    vm.hook_add(UC_HOOK_CODE,hook);vm.emu_start(0x4975f0,0x410101,count=300)
    return vm.reg_read(UC_X86_REG_RAX)&0xff,struct.unpack('<h',vm.mem_read(0x1a0000,2))[0]
tests=[]
for current,slot,balance,expected in ((0,0,0,1),(12,1,0,1),(49,2,0,1),(49,0,1000,1),(50,0,0,0),(51,1,1000,0),(-1,1,1000,0),(0,3,0,0)):
    result,cost=check(current,slot,balance)
    assert result==expected and (not result or cost==0),(current,slot,result,cost)
    tests.append(dict(current=current,slot=slot,balance=balance,allowed=bool(result),cost=cost))
report=dict(drops_before_sha256=hashlib.sha256(before).hexdigest(),drops_after_sha256=hashlib.sha256(payload).hexdigest(),
            added=added,skill_patch=dict(address=0x497753,offset=offset,before=old.hex(),after=new.hex()),tests=tests,
            note='Reconstructed missing gift distributions; not an assertion of original retail reward parity. Client may still display the original fragment cost.')
(OUT/'manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(added=len(added),skill_tests=len(tests),patch=report['skill_patch'])))

