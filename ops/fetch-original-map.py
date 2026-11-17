"""Retry official matching V15 members through the user-supplied MEGA link once."""
from pathlib import Path
import hashlib,importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('mega_zip',ROOT/'ops/inspect-v15-client.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class ExactReader(module.MegaFile):
 def read(self,size=-1):
  size=self.size-self.position if size<0 else min(size,self.size-self.position)
  if not size:return b''
  data=self.range(self.position,size);self.position+=size;return data
reader=ExactReader();out=[]
with zipfile.ZipFile(reader) as archive:
 for name in ['map/model/S048/S048.fsm','data/db/C_Node.ini','data/db/T_Node.ini']:
  info=next(e for e in archive.infolist() if e.filename.lower().replace('\\','/').endswith('/'+name.lower()))
  target=ROOT/'staging/v15-map-original'/name;target.parent.mkdir(parents=True,exist_ok=True)
  raw=archive.read(info);target.write_bytes(raw)
  item={'path':name,'bytes':len(raw),'crc':f'{info.CRC:08x}','sha256':hashlib.sha256(raw).hexdigest()};out.append(item);print(json.dumps(item),flush=True)
(ROOT/'docs/v15-map-original-download.json').write_text(json.dumps(out,indent=2))
