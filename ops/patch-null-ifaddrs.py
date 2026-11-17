"""Guard null ifa_addr entries in legacy x86-64 GetIfAddrs loops.

Keeps the existing IPv4 comparison and branches intact. A trampoline skips an
entry only when its address pointer is null. Original bytes are backed up.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import struct
import sys

def patch(path):
    backup=path.with_name(path.name+'.pre-null-guard')
    if backup.exists():
        raise RuntimeError(f'{backup} exists; refusing a second patch')
    data=bytearray(path.read_bytes())
    if data[:6]!=b'\x7fELF\x02\x01':
        raise RuntimeError('Expected little-endian ELF64')
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
    if header[1:3]!=(2,62):
        raise RuntimeError('Expected static x86-64 ET_EXEC')
    phoff,phsize,phnum=header[5],header[9],header[10]
    headers=[struct.unpack_from('<IIQQQQQQ',data,phoff+i*phsize) for i in range(phnum)]
    notes=[i for i,h in enumerate(headers) if h[0]==4]
    if len(notes)!=1:
        raise RuntimeError('Expected one PT_NOTE program-header slot')
    sites=[]
    for h in headers:
        if h[0]!=1 or not h[1]&1:
            continue
        for match in re.finditer(rb'\x48\x8b\x43\x18\x66\x83\x38\x02\x75.',bytes(data[h[2]:h[2]+h[5]]),re.S):
            offset=h[2]+match.start()+4
            address=h[3]+match.start()+4
            skip=address+6+struct.unpack_from('b',data,offset+5)[0]
            # The original branch must point backward to this loop's next entry.
            if not address-64<=skip<address:
                raise RuntimeError('Unexpected interface-loop branch target')
            sites.append((offset,address,skip))
    if not 1<=len(sites)<=8:
        raise RuntimeError(f'Unexpected guard site count: {len(sites)}')
    align=lambda n:(n+4095)&~4095
    newoff=align(len(data))
    newaddr=align(max(h[3]+h[6] for h in headers if h[0]==1))+4096
    blob=bytearray()
    changes=[]
    def relative(target,next_address):
        return struct.pack('<i',target-next_address)
    for offset,address,skip in sites:
        thunk=newaddr+len(blob)
        code=bytearray(b'\x48\x85\xc0')
        code+=b'\x0f\x84'+relative(skip,thunk+9)
        code+=b'\x66\x83\x38\x02'
        code+=b'\x0f\x85'+relative(skip,thunk+19)
        code+=b'\xe9'+relative(address+6,thunk+24)
        assert len(code)==24
        original=bytes(data[offset:offset+6])
        data[offset:offset+6]=b'\xe9'+relative(thunk,address+5)+b'\x90'
        blob+=code
        changes.append({'site':hex(address),'skip':hex(skip),'thunk':hex(thunk),'original':original.hex()})
    shutil.copy2(path,backup)
    data+=b'\0'*(newoff-len(data))+blob
    struct.pack_into('<IIQQQQQQ',data,phoff+notes[0]*phsize,1,5,newoff,newaddr,newaddr,len(blob),len(blob),4096)
    path.write_bytes(data)
    report={'file':str(path),'original_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'patched_sha256':hashlib.sha256(data).hexdigest(),'guards':changes}
    path.with_name(path.name+'.null-guard.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'file':str(path),'guards':len(sites),'sha256':report['patched_sha256']}))

for name in sys.argv[1:]:
    patch(Path(name))
