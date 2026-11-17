"""Read exception/module/context metadata from the client's minidump, locally."""
from pathlib import Path
import json,struct
p=Path(__file__).resolve().parent.parent/'client/Requiem Aurakingdom/game.dmp';data=p.read_bytes()
assert data[:4]==b'MDMP'
count,directory=struct.unpack_from('<II',data,8)
streams={kind:(size,rva) for kind,size,rva in [struct.unpack_from('<III',data,directory+i*12) for i in range(count)]}
size,rva=streams[6];thread=struct.unpack_from('<I',data,rva)[0];code,flags,record,address,nparams=struct.unpack_from('<IIQQI',data,rva+8)
params=struct.unpack_from('<15Q',data,rva+40)[:nparams]
ctxsize,ctxrva=struct.unpack_from('<II',data,rva+160)
out={'thread':thread,'code':hex(code),'address':hex(address),'parameters':[hex(v) for v in params],'context_size':ctxsize,'streams':list(streams)}
if ctxsize>=204:
 names=['edi','esi','ebx','edx','ecx','eax','ebp','eip','segcs','eflags','esp','segss']
 out['x86_context']={n:hex(v) for n,v in zip(names,struct.unpack_from('<12I',data,ctxrva+156))}
if 4 in streams:
 _,start=streams[4];modules=[]
 for i in range(struct.unpack_from('<I',data,start)[0]):
  base,length,checksum,timestamp,name=struct.unpack_from('<QIIII',data,start+4+i*108)
  if base<=address<base+length:
   lengthname=struct.unpack_from('<I',data,name)[0];modules.append({'name':data[name+4:name+4+lengthname].decode('utf16'),'base':hex(base),'rva':hex(address-base)})
 out['fault_module']=modules
print(json.dumps(out,indent=2))
