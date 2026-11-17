from pathlib import Path
import json
import struct
import subprocess as sp

def q(s):
    r=sp.run(['runuser','-u','postgres','--','psql','-X','-q','-tA','-v','ON_ERROR_STOP=1','-d','FFAccount'],input=s,text=True,capture_output=True,cwd='/tmp',check=True)
    return r.stdout.strip()

path=Path('/root/hxsy/ZoneServer/ZoneServer')
with path.open('rb') as f:
    head=f.read(64);phoff=struct.unpack_from('<Q',head,32)[0];size,count=struct.unpack_from('<HH',head,54)
    f.seek(phoff);headers=f.read(size*count)
    loads=[struct.unpack_from('<IIQQQQQQ',headers,i*size) for i in range(count) if struct.unpack_from('<I',headers,i*size)[0]==1]
    def read(addr,n):
        segment=next(h for h in loads if h[3]<=addr and addr+n<=h[3]+h[5])
        offset=segment[2]+addr-segment[3];f.seek(offset)
        return dict(address=addr,offset=offset,bytes=f.read(n).hex(),segment_flags=segment[1])
    result=dict(sites=[read(0x5849c3,6),read(0x5849f5,5)],stub=read(0x16cc000,64),function=read(0x584760,2083))
result['catalog']=json.loads(q('SELECT coalesce(json_agg(t),\'[]\') FROM dressroom t'))
Path('/root/free-preview-inspection.json').write_text(json.dumps(result))
print(json.dumps(dict(rows=len(result['catalog']),categories=sorted({r['item_category'] for r in result['catalog']}),
    price_min=min(r['price'] for r in result['catalog']),price_max=max(r['price'] for r in result['catalog']),
    sites=result['sites'],stub_is_free=not any(bytes.fromhex(result['stub']['bytes'])))))
