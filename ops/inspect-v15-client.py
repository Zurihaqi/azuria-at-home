"""Read the user-supplied public MEGA ZIP without executing any downloaded code."""
import base64, hashlib, io, json, struct, sys, urllib.request, urllib.error, zipfile
from collections import OrderedDict
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'ops/runtime'))
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
HANDLE='aDoyzLiZ'
KEY='sk6nHC0IfxGuf7q9_RPh-yUfZBZNDE5xh1-4DweXDjU'

class MegaBandwidthLimit(SystemExit):
    """Stop a bulk rebuild immediately; retrying thousands of files cannot fix a quota."""
    pass

class MegaFile(io.RawIOBase):
    quota_blocked=False
    def __init__(self):
        if MegaFile.quota_blocked:raise MegaBandwidthLimit('MEGA bandwidth exhausted; rebuild remains incomplete')
        request=urllib.request.Request('https://g.api.mega.co.nz/cs',data=json.dumps([{'a':'g','g':1,'p':HANDLE}]).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=30) as response:r=json.load(response)[0]
        if not isinstance(r,dict):raise RuntimeError('MEGA link unavailable: '+str(r))
        self.url,self.size,self.position=r['g'],r['s'],0
        words=struct.unpack('>8I',base64.urlsafe_b64decode(KEY+'='*((-len(KEY))%4)))
        self.key=struct.pack('>4I',*[words[i]^words[i+4] for i in range(4)])
        self.iv=int.from_bytes(struct.pack('>4I',words[4],words[5],0,0),'big')
        self.cache=OrderedDict()
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        self.position=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        if not 0<=self.position<=self.size:raise ValueError('ZIP seek outside file')
        return self.position
    def range(self,position,size):
        start=position//16*16;end=position+size-1
        request=urllib.request.Request(self.url+f'/{start}-{end}')
        try:
            with urllib.request.urlopen(request,timeout=90) as response:
                if response.status not in [200,206]:raise ValueError('MEGA range failed')
                raw=response.read(end-start+2)
        except urllib.error.HTTPError as exc:
            if exc.code==509:
                MegaFile.quota_blocked=True
                raise MegaBandwidthLimit('MEGA bandwidth exhausted (HTTP 509); rebuild remains incomplete') from None
            raise
        if len(raw)!=end-start+1:raise ValueError('MEGA returned the wrong range length')
        decryptor=Cipher(algorithms.AES(self.key),modes.CTR((self.iv+start//16).to_bytes(16,'big'))).decryptor()
        return (decryptor.update(raw)+decryptor.finalize())[position-start:]
    def read(self,size=-1):
        size=self.size-self.position if size<0 else min(size,self.size-self.position)
        if not size:return b''
        block_size=4*1024*1024
        if size>=block_size:
            data=self.range(self.position,size)
        else:
            chunks=[];cursor=self.position;left=size
            while left:
                base=cursor//block_size*block_size
                if base not in self.cache:
                    self.cache[base]=self.range(base,min(block_size,self.size-base))
                    if len(self.cache)>8:self.cache.popitem(last=False)
                self.cache.move_to_end(base)
                block=self.cache[base];offset=cursor-base;count=min(left,len(block)-offset)
                chunks.append(block[offset:offset+count]);cursor+=count;left-=count
            data=b''.join(chunks)
        self.position+=size
        return data

if __name__=='__main__':
    remote=MegaFile()
    with zipfile.ZipFile(remote) as archive:
        manifest=[dict(name=e.filename,size=e.file_size,packed=e.compress_size,crc=f'{e.CRC:08x}') for e in archive.infolist()]
        (ROOT/'docs/v15-original-archive.json').write_text(json.dumps(dict(source='https://mega.nz/file/'+HANDLE,bytes=remote.size,files=manifest),indent=2))
        wanted=sys.argv[1:]
        if not wanted:
            print(json.dumps([x for x in manifest if any(k in x['name'].lower() for k in ['game.bin','c_mission.ini','t_mission.ini','c_syssetup.ini'])],indent=2))
        for name in wanted:
            info=next(e for e in archive.infolist() if e.filename.lower().endswith(name.lower()))
            destination=ROOT/'staging/v15-original'/Path(info.filename.replace('\\','/'))
            destination.resolve().relative_to((ROOT/'staging/v15-original').resolve())
            destination.parent.mkdir(parents=True,exist_ok=True)
            data=archive.read(info)  # zipfile checks member CRC after decompression.
            destination.write_bytes(data)
            print(json.dumps(dict(file=str(destination),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())),flush=True)
