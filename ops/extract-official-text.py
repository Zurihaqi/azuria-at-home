"""Decode publisher PKG ZLIBX streams; no downloaded executables are run.

Format reference: QuickBMS tinflatex.c (Luigi Auriemma / Joergen Ibsen),
https://github.com/LittleBigBug/QuickBMS/blob/master/src/compression/tinflatex.c
This independent bounded decoder supports the extended 286/287 length codes.
"""
from pathlib import Path
import hashlib,json,struct,zlib
ROOT=Path(__file__).resolve().parent.parent

class Bits:
 def __init__(self,data):self.data=data;self.pos=0;self.value=0;self.count=0
 def read(self,n):
  while self.count<n:
   if self.pos>=len(self.data):raise ValueError('Truncated DEFLATEX stream')
   self.value|=self.data[self.pos]<<self.count;self.pos+=1;self.count+=8
  value=self.value&((1<<n)-1);self.value>>=n;self.count-=n;return value
 def align(self):self.read(self.count%8)

def tree(lengths):
 counts=[0]*16
 for length in lengths:
  assert 0<=length<16
  if length:counts[length]+=1
 codes=[0]*16;value=0
 for length in range(1,16):value=(value+counts[length-1])<<1;codes[length]=value
 lookup={}
 for symbol,length in enumerate(lengths):
  if length:
   code=codes[length];codes[length]+=1
   reverse=int(f'{code:0{length}b}'[::-1],2)
   lookup[length,reverse]=symbol
 def decode(bits):
  code=0
  for length in range(1,16):
   code|=bits.read(1)<<(length-1)
   if (length,code) in lookup:return lookup[length,code]
  raise ValueError('Invalid Huffman code')
 return decode

def bases(delta,first):
 extra=[0]*288
 for i in range(288-delta):extra[i+delta]=i//delta
 base=[];value=first
 for n in extra:base.append(value);value+=1<<n
 return extra,base

def inflate(data,size):
 bits=Bits(data[2:]);out=bytearray();length_bits,length_base=bases(4,3);distance_bits,distance_base=bases(2,1)
 length_bits[28]=0;length_base[28]=258
 while True:
  final=bits.read(1);kind=bits.read(2)
  if kind==0:
   bits.align();n=bits.read(16);inverse=bits.read(16);assert n^inverse==65535
   assert len(out)+n<=size
   out.extend(bits.read(8) for _ in range(n))
  else:
   if kind==1:literal=tree([8]*144+[9]*112+[7]*24+[8]*8);distance=tree([5]*32)
   elif kind==2:
    nl=bits.read(5)+257;nd=bits.read(5)+1;nc=bits.read(4)+4
    order=[16,17,18,0,8,7,9,6,10,5,11,4,10-1,5-1,11,3,12] # replaced below by RFC order
    order=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15]
    lengths=[0]*19
    for i in range(nc):lengths[order[i]]=bits.read(3)
    code_tree=tree(lengths);lengths=[]
    while len(lengths)<nl+nd:
     symbol=code_tree(bits)
     if symbol<16:lengths.append(symbol)
     elif symbol==16:
      assert lengths;lengths.extend([lengths[-1]]*(bits.read(2)+3))
     elif symbol==17:lengths.extend([0]*(bits.read(3)+3))
     elif symbol==18:lengths.extend([0]*(bits.read(7)+11))
    assert len(lengths)==nl+nd
    literal,distance=tree(lengths[:nl]),tree(lengths[nl:])
   else:raise ValueError('Reserved DEFLATE block')
   while True:
    symbol=literal(bits)
    if symbol<256:
     assert len(out)<size;out.append(symbol)
    elif symbol==256:break
    else:
     code=symbol-257;length=length_base[code]+bits.read(length_bits[code]);code=distance(bits)
     back=distance_base[code]+bits.read(distance_bits[code]);assert 0<back<=len(out) and len(out)+length<=size
     for _ in range(length):out.append(out[-back])
  if final:break
 assert len(out)==size,(len(out),size)
 # Publisher stream uses a nonstandard window header, but retains Adler32.
 assert zlib.adler32(out)&0xffffffff==int.from_bytes(data[-4:],'big'),'Adler32 mismatch'
 return bytes(out)

if __name__=='__main__':
 destination=ROOT/'staging/official-text';destination.mkdir(exist_ok=True);report=[]
 for entry in json.loads((ROOT/'docs/official-text-package-index.json').read_text()):
  blob=(ROOT/'downloads/official-client/pkg'/f'pkg{entry["pkg"]:03d}.pkg').read_bytes()
  packed=blob[entry['offset']:entry['offset']+entry['packed']]
  data=inflate(packed,entry['size']);name=entry['name'].split('\\')[-1]
  (destination/name).write_bytes(data)
  report.append(dict(name=name,size=len(data),sha256=hashlib.sha256(data).hexdigest(),adler32_verified=True))
  print(name,len(data),repr(data[:100]),flush=True)
 (ROOT/'docs/official-text-extraction.json').write_text(json.dumps(report,indent=2))
