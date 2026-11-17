from pathlib import Path
import json
root=Path(__file__).resolve().parent.parent
def table(path):
    return {int(x.split('|',1)[0]):x.split('|') for x in path.read_text(encoding='utf-8',errors='replace').splitlines() if x.split('|',1)[0].isdigit()}
items=table(root/'staging/ultimate/hxsy/Data/db/S_Item.ini')
names=table(root/'staging/ultimate/hxsy/Data/db/T_Item.ini')
def num(v):
    try:return float(v.strip() or 0)
    except:return 0
def summary(r):
    return {'id':int(r[0]),'name':names.get(int(r[0]),['',''])[1],'type':r[8],'level':r[13],'grade':r[3],'stats':{str(i):r[i] for i in range(26,44) if r[i]}}
result={}
for typ in ['24','1','2','3','4','5','6','7','25']:
    candidates=[r for r in items.values() if len(r)>43 and r[8]==typ and 1<=num(r[13])<=150]
    candidates.sort(key=lambda r:(num(r[13]),r[3],sum(num(r[i]) for i in [28,38,39])),reverse=True)
    result[typ]=[summary(r) for r in candidates[:6]]
(root/'docs/gear-candidates.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
