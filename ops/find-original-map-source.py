from pathlib import Path
import json,struct
ROOT=Path(__file__).resolve().parent.parent;raw=(ROOT/'downloads/official-client/pkg/pkg.idx').read_bytes();out=[]
for offset in range(292,len(raw)-591,592):
 name=raw[offset+60:offset+320].split(b'\0',1)[0].decode('utf8',errors='replace')
 if not name.lower().replace('\\','/').endswith('/s048.fsm'):continue
 folder=raw[offset+320:offset+580].split(b'\0',1)[0].decode('utf8',errors='replace')
 out.append({'name':name,'folder':folder,'offset':struct.unpack_from('<I',raw,offset+4)[0],'packed':struct.unpack_from('<I',raw,offset+12)[0],'size':struct.unpack_from('<I',raw,offset+56)[0],'pkg':struct.unpack_from('<I',raw,offset+584)[0]})
(ROOT/'docs/original-s048-package.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
