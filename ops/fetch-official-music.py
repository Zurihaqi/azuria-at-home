from pathlib import Path
import concurrent.futures,hashlib,json,struct,sys,time,urllib.request,zlib
root=Path(__file__).resolve().parent.parent
archive=json.loads((root/'downloads/music-installer/remote-archive.json').read_text())
index=json.loads((root/'downloads/music-installer/music-index.json').read_text())
requested=[x['name'][:-4].lower() for x in index] if '--all' in sys.argv else json.loads((root/'docs/music-download-report.json').read_text())['requested']
byname={x['name'].lower():x for x in index}
def get(start,size):
 req=urllib.request.Request(archive['url'],headers={'Range':f'bytes={start}-{start+size-1}'})
 with urllib.request.urlopen(req,timeout=60) as r:
  assert r.status==206
  data=r.read()
 assert len(data)==size
 return data
bases={}
for volume in {byname[n+'.ogg']['volume'] for n in requested if n+'.ogg' in byname}:
 entry=next(x for x in archive['entries'] if x['name']==f'data{volume}.cab')
 assert entry['compression']==0
 header=get(entry['zip_header_offset'],512)
 assert header[:4]==b'PK\x03\x04'
 namelen,extra=struct.unpack_from('<HH',header,26)
 bases[volume]=entry['zip_header_offset']+30+namelen+extra
dest=root/'downloads/music';dest.mkdir(exist_ok=True)
def fetch(name):
 item=byname[name+'.ogg'];path=dest/(name+'.ogg')
 if path.exists():data=path.read_bytes()
 else:
  packed=get(bases[item['volume']]+item['offset'],item['packed'])
  if item['flags']&4:
   pos=0;parts=[]
   while pos<len(packed):
    length=struct.unpack_from('<H',packed,pos)[0];pos+=2
    parts.append(zlib.decompress(packed[pos:pos+length]+b'\0',-15));pos+=length
   data=b''.join(parts)
  else:data=packed
  assert len(data)==item['size'] and hashlib.md5(data).hexdigest()==item['md5'],name
  assert data.startswith(b'OggS') and b'vorbis' in data[:256],name
  path.write_bytes(data)
 assert hashlib.md5(data).hexdigest()==item['md5']
 return {'name':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'source':archive['url'],'cabinet':item['volume'],'cabinet_offset':item['offset']}
available=[n for n in requested if n+'.ogg' in byname]
downloaded=[];failed=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 futures={pool.submit(fetch,n):n for n in available}
 for future in concurrent.futures.as_completed(futures):
  try:downloaded.append(future.result());print('Verified original',futures[future],flush=True)
  except Exception as e:failed.append({'name':futures[future],'error':str(e)});print('Failed',futures[future],e,flush=True)
report={'source':archive['url'],'downloaded':downloaded,'failed':failed,'unavailable':[n for n in requested if n+'.ogg' not in byname]}
(root/('docs/official-music-full-report.json' if '--all' in sys.argv else 'docs/official-music-report.json')).write_text(json.dumps(report,indent=2))
print(json.dumps({'downloaded':len(downloaded),'failed':failed,'unavailable':report['unavailable']},indent=2))
