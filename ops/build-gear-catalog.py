"""Build a reproducible catalog from compatible server/client equipment definitions."""
from pathlib import Path
import collections,hashlib,json,re
root=Path(__file__).resolve().parent.parent
def read_items(paths):
    result={}
    for path in paths:
        text=path.read_bytes().decode('cp950',errors='replace')
        for chunk in re.split(r'(?m)(?=^[0-9]+\|)',text)[1:]:
            row=chunk.rstrip().split('|')
            if len(row)!=67 or not row[8].isdigit():
                continue
            ident=int(row[0])
            if ident in result and result[ident][8]!=row[8]:
                raise RuntimeError(f'Conflicting item type for {ident}')
            result[ident]=row
    return result
server=read_items([root/'staging/ultimate/hxsy/Data/db/S_Item.ini',root/'staging/ultimate/hxsy/Data/db/S_ItemMall.ini'])
client=read_items([root/'client/Requiem Aurakingdom/data/db/C_Item.ini',root/'client/Requiem Aurakingdom/data/db/C_ItemMall.ini'])
weapons=set(range(7,25))
armor=set(range(1,7))|set(range(31,37))
accessories=set(range(37,41))|set(range(42,46))|{7001,7003,7004,7005,7006,7007,7008}
catalog=[]
for ident,row in sorted(server.items()):
    typ=int(row[8]);other=client.get(ident)
    if typ not in weapons|armor|accessories or not other or other[8]!=row[8] or other[13]!=row[13]:
        continue
    # Require a model/icon for display, a numeric supported requirement, and a real item.
    if not row[1] or not row[13].strip().isdigit() or int(row[13])>150:
        continue
    detail=1 if typ in weapons else 2 if typ in armor else 3
    catalog.append({'id':ident,'type':typ,'required_level':int(row[13]),'detail_type':detail})
catalog.sort(key=lambda r:(r['detail_type'],r['type'],r['required_level'],r['id']))
indexes=collections.Counter()
for row in catalog:
    indexes[row['detail_type']]+=1
    row['index']=indexes[row['detail_type']]
assert catalog and max(indexes.values())<32767
output={'marker':'codex:gear-catalog:v1','item_group':6,'money_unit':1,'price':1,'sections':{'1':'Weapons','2':'Armor & Costumes','3':'Accessories & Tools'},'counts':dict(indexes),'items':catalog}
(root/'docs/gear-catalog.json').write_text(json.dumps(output,indent=2))
labels={2176:b'Gear Catalog',3113:b'Weapons',3133:b'Armor & Costumes',3134:b'Accessories & Tools'}
path=root/'client/Requiem Aurakingdom/data/db/T_TextIndex.ini'
backup=root/'private/client-original/T_TextIndex.ini'
if not backup.exists():backup.write_bytes(path.read_bytes())
data=backup.read_bytes()
for ident,label in labels.items():
    data,n=re.subn(rb'(?m)^'+str(ident).encode()+rb'\|[^\r\n]*',str(ident).encode()+b'|'+label+b'|',data)
    assert n==1,(ident,n)
path.chmod(0o666)
with path.open('r+b') as stream:stream.write(data);stream.truncate()
print(json.dumps({'catalog_items':len(catalog),'sections':dict(indexes),'client_label_sha256':hashlib.sha256(data).hexdigest()}))
