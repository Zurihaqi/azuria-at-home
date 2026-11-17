"""Read verified original installer cabinet members without running its installer."""
from pathlib import Path, PureWindowsPath
import argparse, hashlib, json, struct, time, urllib.request, zlib

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'downloads/music-installer'
ARCHIVE=json.loads((SOURCE/'remote-archive.json').read_text())
DEST=ROOT/'downloads/official-client'

def read_name(blob,offset):
    if not 0<=offset<len(blob):raise ValueError('Invalid cabinet name offset')
    end=offset
    while end+2<=len(blob) and blob[end:end+2]!=b'\0\0':end+=2
    if end+2>len(blob):raise ValueError('Unterminated cabinet name')
    return blob[offset:end].decode('utf-16le')

def index():
    blob=(SOURCE/'data1.hdr').read_bytes()
    base=0x281f
    directories=[read_name(blob,base+struct.unpack_from('<I',blob,base+i*4)[0]) for i in range(35)]
    out=[]
    # File group "Files" starts at descriptor index 25; preceding entries are installer support.
    for i in range(25,5008):
        off=0x28ab+i*0x57
        flags,size,packed,offset=struct.unpack_from('<HQQQ',blob,off)
        if flags&8:continue
        name_offset=struct.unpack_from('<I',blob,off+58)[0]
        if not name_offset:continue
        name=read_name(blob,base+name_offset)
        directory=struct.unpack_from('<H',blob,off+62)[0]
        volume=struct.unpack_from('<H',blob,off+85)[0]
        path=PureWindowsPath(directories[directory])/name
        if volume in [2,3,4] and not path.is_absolute() and '..' not in path.parts and '://' not in str(path):
            out.append(dict(index=i,path=path.as_posix(),flags=flags,size=size,packed=packed,offset=offset,volume=volume,md5=blob[off+26:off+42].hex()))
    return out

def get(start,size):
    for attempt in range(4):
        try:
            req=urllib.request.Request(ARCHIVE['url'],headers={'Range':f'bytes={start}-{start+size-1}'})
            with urllib.request.urlopen(req,timeout=90) as response:
                if response.status!=206:raise ValueError('Source did not honor byte range')
                data=response.read()
            if len(data)!=size:raise ValueError('Truncated cabinet range')
            return data
        except Exception:
            if attempt==3:raise
            time.sleep(1+attempt)

BASES={}
def fetch(item):
    path=DEST/item['path']
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and hashlib.md5(path.read_bytes()).hexdigest()==item['md5']:return path
    volume=item['volume']
    if volume not in BASES:
        entry=next(e for e in ARCHIVE['entries'] if e['name']==f'data{volume}.cab')
        header=get(entry['zip_header_offset'],512)
        assert header[:4]==b'PK\x03\x04' and entry['compression']==0
        name,extra=struct.unpack_from('<HH',header,26)
        BASES[volume]=entry['zip_header_offset']+30+name+extra
    if item['flags']&1:raise ValueError('Split-cabinet member requires full volume extraction: '+item['path'])
    packed=get(BASES[volume]+item['offset'],item['packed']) if item['packed'] else b''
    if item['flags']&4:
        chunks=[];position=0
        while position<len(packed):
            length=struct.unpack_from('<H',packed,position)[0];position+=2
            chunks.append(zlib.decompress(packed[position:position+length]+b'\0',-15));position+=length
        data=b''.join(chunks)
    else:data=packed
    assert len(data)==item['size'] and hashlib.md5(data).hexdigest()==item['md5'],item['path']
    temporary=path.with_suffix(path.suffix+'.partial');temporary.write_bytes(data);temporary.replace(path)
    return path

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('files',nargs='*');args=parser.parse_args()
    entries=index();DEST.mkdir(exist_ok=True)
    (DEST/'cabinet-index.json').write_text(json.dumps(entries,indent=2))
    for name in args.files:
        item=next(x for x in entries if x['path'].lower()==name.lower())
        path=fetch(item)
        print(json.dumps(dict(file=str(path),size=path.stat().st_size,md5=item['md5'])),flush=True)
