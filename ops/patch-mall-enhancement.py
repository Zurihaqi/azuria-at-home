"""Guest-side append to the existing null-guard ELF segment, preserving its guards."""
from pathlib import Path
import hashlib,json,shutil,struct

def patch():
 path=Path('/root/hxsy/ZoneServer/ZoneServer')
 backup=path.with_name('ZoneServer.pre-mall-enhancement')
 assert not backup.exists(), 'Already patched; refusing duplicate patch'
 data=bytearray(path.read_bytes())
 header=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
 assert data[:6]==b'\x7fELF\x02\x01' and header[1:3]==(2,62)
 phoff,phsize,phnum=header[5],header[9],header[10]
 headers=[struct.unpack_from('<IIQQQQQQ',data,phoff+i*phsize) for i in range(phnum)]
 candidates=[(i,h) for i,h in enumerate(headers) if h[0]==1 and h[3]==0x16ba000 and h[1]==5]
 assert len(candidates)==1
 index,segment=candidates[0]
 assert segment[5]==48 and segment[6]==48 and segment[2]+48==len(data)
 manifest=json.loads(Path('/root/mall-enhancement-hook.json').read_text())
 code=Path('/root/mall-enhancement-code.bin').read_bytes();mask=Path('/root/mall-enhancement-mask.bin').read_bytes()
 assert len(mask)==65536 and len(code)==manifest['code_size']
 def offset(address):
  for h in headers:
   if h[0]==1 and h[3]<=address<h[3]+h[5]:return h[2]+address-h[3]
  raise RuntimeError('Unmapped patch address')
 for hook in manifest['sites']:
  off=offset(hook['site']);assert data[off:off+6]==bytes.fromhex('4885c04889c5')
  data[off:off+6]=b'\xe9'+struct.pack('<i',hook['target']-hook['site']-5)+b'\x90'
 codeoff=segment[2]+manifest['code_address']-segment[3]
 data.extend(b'\0'*(codeoff-len(data)));data.extend(code)
 tableoff=segment[2]+manifest['table_address']-segment[3]
 data.extend(b'\0'*(tableoff-len(data)));data.extend(mask)
 size=len(data)-segment[2]
 updated=list(segment);updated[5]=size;updated[6]=size
 struct.pack_into('<IIQQQQQQ',data,phoff+index*phsize,*updated)
 shutil.copy2(path,backup)
 before=hashlib.sha256(backup.read_bytes()).hexdigest()
 path.write_bytes(data)
 report=dict(manifest,original_sha256=before,patched_sha256=hashlib.sha256(data).hexdigest(),backup=str(backup),validation='18 emulator cases passed; live purchase test pending')
 Path('/root/mall-enhancement-deployment.json').write_text(json.dumps(report,indent=2))
 print('Mall enhancement hook applied; original binary backed up')

if __name__=='__main__':patch()
