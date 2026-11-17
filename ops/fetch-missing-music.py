"""Recover missing game music from the soundtrack wiki's original Ogg uploads."""
from pathlib import Path
import concurrent.futures,hashlib,json,re,time,urllib.parse,urllib.request
root=Path(__file__).resolve().parent.parent
bgm=root/'client/Requiem Aurakingdom/bgm'
text=(root/'staging/ultimate/hxsy/Data/db/S_Node.ini').read_bytes().decode('cp950',errors='replace')
rows=[r for ch in re.split(r'(?m)(?=^[0-9]+\|)',text)[1:] if len(r:=ch.rstrip().split('|'))==68]
missing=sorted({x for r in rows for x in r[14:18] if x and not (bgm/(x+'.ogg')).exists()})
headers={'User-Agent':'Mozilla/5.0 (Aura Kingdom local client repair)'}
found={};unavailable=[]
for start in range(0,len(missing),40):
 batch=missing[start:start+40]
 params={'action':'query','titles':'|'.join('File:'+name[0].upper()+name[1:]+'.ogg' for name in batch),'prop':'imageinfo','iiprop':'url|size|sha1','format':'json'}
 url='https://aurakingdom.fandom.com/api.php?'+urllib.parse.urlencode(params)
 with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=30) as r:result=json.load(r)
 for page in result['query']['pages'].values():
  name=page['title'][5:-4].lower()
  if page.get('imageinfo'):found[name]=page['imageinfo'][0]
  else:unavailable.append(name)
destination=root/'downloads/music';destination.mkdir(parents=True,exist_ok=True)
def fetch(pair):
 name,info=pair;path=destination/(name+'.ogg')
 if not path.exists():
  for attempt in range(3):
   try:
    with urllib.request.urlopen(urllib.request.Request(info['url'],headers=headers),timeout=45) as r:data=r.read()
    assert data.startswith(b'OggS') and b'vorbis' in data[:256],name
    assert len(data)==info['size'],(name,len(data),info['size'])
    path.write_bytes(data);break
   except Exception:
    if attempt==2:raise
    time.sleep(1)
 data=path.read_bytes()
 assert data.startswith(b'OggS')
 return {'name':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'source':info['url']}
downloaded=[];failed=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 futures={pool.submit(fetch,p):p[0] for p in found.items()}
 for future in concurrent.futures.as_completed(futures):
  name=futures[future]
  try:downloaded.append(future.result());print('Downloaded',name,flush=True)
  except Exception as e:failed.append({'name':name,'error':str(e)});print('Failed',name,str(e),flush=True)
report={'requested':missing,'downloaded':downloaded,'unavailable':unavailable,'failed':failed}
(root/'docs/music-download-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'downloaded':len(downloaded),'unavailable':unavailable,'failed':failed},indent=2))
