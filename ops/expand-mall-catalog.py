from pathlib import Path
import collections,json,re
root=Path(__file__).resolve().parent.parent
def read(path,fields=None):
 out={}
 for chunk in re.split(r'(?m)(?=^[0-9]+\|)',path.read_bytes().decode('cp950',errors='replace'))[1:]:
  row=chunk.rstrip().split('|')
  if fields is None or len(row)==fields:out[int(row[0])]=row
 return out
s={};c={};names={}
for name in ['Item','ItemMall']:
 s.update(read(root/f'staging/ultimate/hxsy/Data/db/S_{name}.ini',67))
 c.update(read(root/f'client/Requiem Aurakingdom/data/db/C_{name}.ini',67))
 names.update({i:r[1] for i,r in read(root/f'client/Requiem Aurakingdom/data/db/T_{name}.ini').items()})
catalog=json.loads((root/'docs/gear-catalog.json').read_text())
items={r['id']:r for r in catalog['items']}
for ident,row in s.items():
 other=c.get(ident)
 if not other or ident>65535 or not row[8].isdigit() or row[8]!=other[8]:continue
 typ=int(row[8])
 if typ not in set(range(31,37))|{41,70}:continue
 if row[13]!=other[13] or row[21]!=other[21] or not row[1]:continue
 # Type 70 is the native Eidolon summoning-key class; exclude key fragments and containers.
 if typ==70 and not re.search(r'Key of Gaia',names.get(ident,''),re.I):continue
 level=int(row[13] or 0)
 if level>150:continue
 items[ident]={'id':ident,'type':typ,'required_level':level,'name':names.get(ident,row[7])}
catalog['items']=list(items.values())
(root/'docs/gear-catalog-expanded.json').write_text(json.dumps(catalog,indent=2))
print(json.dumps({'items':len(items),'added_types':dict(collections.Counter(x['type'] for x in items.values() if x['type'] in set(range(31,37))|{41,70}))},indent=2))
