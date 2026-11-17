"""Zero-price fitting-room support with bounded native-code emulation."""
from pathlib import Path
import json
import struct
import sys
sys.path.insert(0,str(Path(__file__).parent/'runtime'))
from keystone import Ks,KS_ARCH_X86,KS_MODE_64
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn.x86_const import *

ROOT=Path(__file__).resolve().parent.parent
source=json.loads((ROOT/'staging/free-preview-inspection.json').read_text())
stub=0x16cc000
assembler=Ks(KS_ARCH_X86,KS_MODE_64)
code=bytes(assembler.asm('test r13d,r13d; jz 0x584d30; mov edx,r13d; xor esi,esi; jmp 0x5849fa',stub)[0])
assert len(code)<=64 and set(bytes.fromhex(source['stub']['bytes']))=={0}
patches=[]
for entry,new in zip(source['sites'],(bytes.fromhex('0f8825020000'),b'\xe9'+struct.pack('<i',stub-0x5849f5-5))):
    assert len(new)==len(bytes.fromhex(entry['bytes']))
    patches.append(dict(address=entry['address'],offset=entry['offset'],before=entry['bytes'],after=new.hex()))
patches.append(dict(address=stub,offset=source['stub']['offset'],before='00'*len(code),after=code.hex()))
native=bytearray.fromhex(source['function']['bytes'])
for entry in patches[:2]:
    pos=entry['address']-source['function']['address']
    assert native[pos:pos+len(bytes.fromhex(entry['before']))]==bytes.fromhex(entry['before'])
    native[pos:pos+len(bytes.fromhex(entry['after']))]=bytes.fromhex(entry['after'])

def emulate(price,quantity,balance,full=False):
    uc=Uc(UC_ARCH_X86,UC_MODE_64)
    for addr,size in ((0x584000,0x1000),(stub,0x1000),(0x9ff000,0x1000),(0xa8c000,0x1000),(0x100000,0x20000),(0x300000,0x2000)):
        uc.mem_map(addr,size)
    uc.mem_write(source['function']['address'],bytes(native));uc.mem_write(stub,code)
    for addr in (0x9ff910,0x9ffb60,0xa8c7f0):uc.mem_write(addr,b'\xc3')
    uc.mem_write(0x30100c,struct.pack('<i',price))
    for reg,value in ((UC_X86_REG_RSP,0x110000),(UC_X86_REG_R12,0x301000),(UC_X86_REG_R14,0x300000),(UC_X86_REG_RBX,quantity)):
        uc.reg_write(reg,value)
    outcome=[];debits=[]
    stops={0x584d30:'delivery',0x584bee:'invalid',0x584d0d:'funds',0x584ea4:'full'}
    def hook(emu,address,size,data):
        if address in stops:outcome.append(stops[address]);emu.emu_stop()
        elif address==0x9ff910:emu.reg_write(UC_X86_REG_RAX,balance)
        elif address==0xa8c7f0:emu.reg_write(UC_X86_REG_RAX,0xffff if full else 0)
        elif address==0x9ffb60:
            amount=emu.reg_read(UC_X86_REG_EDX);amount=amount-2**32 if amount>=2**31 else amount
            debits.append(amount);emu.reg_write(UC_X86_REG_RAX,1)
    uc.hook_add(UC_HOOK_CODE,hook)
    uc.emu_start(0x5849b7,0x585000,count=150)
    assert outcome
    return outcome[0],debits

cases=[(0,1,0,False,'delivery',[]),(0,20,0,False,'delivery',[]),
       (0,1,100,False,'delivery',[]),(0,1,0,True,'full',[]),
       (-1,1,100,False,'invalid',[]),(22,1,0,False,'funds',[]),
       (22,1,100,False,'delivery',[-22]),(22,3,100,False,'delivery',[-66]),
       (22,5,100,False,'funds',[]),(22,1,100,True,'full',[])]
for price,quantity,balance,full,want,charges in cases:
    actual=emulate(price,quantity,balance,full)
    assert actual==(want,charges),(price,quantity,balance,full,actual)
manifest=dict(patches=patches,catalog_rows=len(source['catalog']),tests_passed=len(cases),
              behavior='Price zero delivers normally without voucher debit; negative prices, paid purchases and full-bag checks retain their native guards.')
(ROOT/'staging/free-preview-patch.json').write_text(json.dumps(manifest,indent=2)+'\n')
(ROOT/'docs/free-preview-patch.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(tests_passed=len(cases),patch_bytes=sum(len(bytes.fromhex(p['after'])) for p in patches),catalog_rows=manifest['catalog_rows'])))
