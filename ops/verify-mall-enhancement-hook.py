"""Emulate hook control flow and ABI with mocked server APIs."""
from pathlib import Path
import json,struct,sys
sys.path.insert(0,str(Path(__file__).parent/'runtime'))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_INVALID
from unicorn.x86_const import *
root=Path(__file__).resolve().parent.parent
manifest=json.loads((root/'docs/mall-enhancement-hook.json').read_text())
code=(root/'ops/mall-enhancement-code.bin').read_bytes();mask=(root/'ops/mall-enhancement-mask.bin').read_bytes()
items=json.loads((root/'docs/gear-catalog-expanded.json').read_text())['items']
ids={t:next(x['id'] for x in items if x['type']==t) for t in [6,7,31,37,41,70]}
cases=0
for hook in manifest['sites']:
 for typ,quality,group,null in [(7,3,6,False),(7,1,6,False),(6,3,6,False),(37,3,6,False),(31,3,6,False),(41,3,6,False),(70,3,6,False),(7,3,1,False),(7,3,6,True)]:
  u=Uc(UC_ARCH_X86,UC_MODE_64)
  u.mem_map(0x400000,0x1300000);u.mem_map(0x2000000,0x20000)
  u.mem_write(manifest['code_address'],code);u.mem_write(manifest['table_address'],mask)
  stack=0x2010000;item=0x2001000;template=0x2002000;event=0x2003000;char=0x2004000;container=0x2007000;db=0x2008000;packet=0x2009000
  u.mem_write(item+16,struct.pack('<Q',template));u.mem_write(template+8,struct.pack('<H',ids[typ]));u.mem_write(item+64,struct.pack('<H',quality))
  u.mem_write(event+0x34,struct.pack('<H',group));u.mem_write(char+0x38,struct.pack('<I',50000001));u.mem_write(stack+0x40,struct.pack('<H',12))
  for addr,value in [(0x16807f0,0x200a000),(0x16902a0,db),(db+0x40,0x200b000),(db+0x18,0x200c000)]:u.mem_write(addr,struct.pack('<Q',value))
  regs={UC_X86_REG_RAX:0 if null else item,UC_X86_REG_RBX:event,UC_X86_REG_R12:char,UC_X86_REG_R13:2,UC_X86_REG_R14:container,UC_X86_REG_R15:0x12345678,UC_X86_REG_RSP:stack,
        UC_X86_REG_RCX:11,UC_X86_REG_RDX:22,UC_X86_REG_RSI:33,UC_X86_REG_RDI:44,UC_X86_REG_R8:55,UC_X86_REG_R9:66,UC_X86_REG_R10:77,UC_X86_REG_R11:88}
  for reg,value in regs.items():u.reg_write(reg,value)
  calls=[]
  api={0x4b2c20:'fortify',0x4a9da0:'attrs',0x8a2620:'persist_stars',0x88dc10:'flush',0xdf0a40:'allocate',0x609650:'notify'}
  def intercept(uc,address,size,data):
   if address==hook['site']+6:uc.emu_stop();return
   if address not in api:return
   sp=uc.reg_read(UC_X86_REG_RSP);assert sp%16==8,('misaligned call',hex(address),hex(sp))
   name=api[address];calls.append(name)
   args=[uc.reg_read(r) for r in [UC_X86_REG_RDI,UC_X86_REG_RSI,UC_X86_REG_RDX,UC_X86_REG_RCX,UC_X86_REG_R8]]
   if name=='fortify':assert args[1:]==[char,container,12,2]
   if name=='attrs':assert args[1:3]==[char,item]
   if name=='persist_stars':assert args[1:]==[50000001,2,12,5]
   if name=='notify':assert args[:3]==[char,packet+16,1];assert uc.mem_read(packet+8,6)==struct.pack('<HHH',2,12,5)
   ret=struct.unpack('<Q',uc.mem_read(sp,8))[0]
   for r in [UC_X86_REG_RAX,UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_RSI,UC_X86_REG_RDI,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_R10,UC_X86_REG_R11]:uc.reg_write(r,0xabcdef)
   uc.reg_write(UC_X86_REG_RAX,packet if name=='allocate' else 0)
   uc.reg_write(UC_X86_REG_RSP,sp+8);uc.reg_write(UC_X86_REG_RIP,ret)
  u.hook_add(UC_HOOK_CODE,intercept)
  def invalid(uc,access,address,size,value,data):
   print('Invalid access',hex(address),'at',hex(uc.reg_read(UC_X86_REG_RIP)),'type',typ,'calls',calls);return False
  u.hook_add(UC_HOOK_MEM_INVALID,invalid)
  u.emu_start(hook['target'],hook['site']+6,count=20000)
  for reg,value in regs.items():assert u.reg_read(reg)==value,(hex(hook['site']),typ,reg,u.reg_read(reg),value)
  assert u.reg_read(UC_X86_REG_RBP)==regs[UC_X86_REG_RAX]
  active=not null and group==6
  assert calls.count('fortify')==(30 if active and mask[ids[typ]]&1 else 0)
  stars=active and mask[ids[typ]]&2 and quality in [2,3,5,6]
  assert calls.count('persist_stars')==int(bool(stars))
  assert struct.unpack('<H',u.mem_read(item+200,2))[0]==(5 if stars else 0)
  cases+=1
print(f'Passed {cases} emulated delivery cases: ABI, slot/container, eligibility, category isolation, null return, both hook sites.')
