"""Build matching Guitar templates and verified V15 skill/mastery manifests."""
from pathlib import Path
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parent.parent
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db'
OUT=ROOT/'staging/guitar'
DATA=ROOT/'staging/ultimate/hxsy/Data/db'

def records(path):
    return {int(row[0]):row for block in re.split(r'(?m)(?=^\d+\|)',path.read_bytes().decode('cp950',errors='surrogateescape'))[1:]
            if len(row:=block.rstrip('\r\n').split('|'))>1 and row[0].isdigit()}

server=records(OUT/'source/S_Item.ini')
client=records(CLIENT/'C_Item.ini')
occupied=set(server)|set(client)
for path in (DATA/'S_ItemMall.ini',CLIENT/'C_ItemMall.ini'):
    occupied.update(records(path))
ident=next(i for i in range(61604,65535) if i not in occupied)
base=33915
assert server[base][8]==client[base][8]=='22'
assert server[61586][21]==client[61586][21]
title="Zrymund's Astral Sovereign - Worldshatter Guitar"
description='Requires SLv30. Sovereign Guitar: PEN +999%; Armor Piercing +500; life steal, critical damage, movement speed and 100% damage reflection.'
files=[]
for label,path in (('S_Item.ini',OUT/'source/S_Item.ini'),('C_Item.ini',CLIENT/'C_Item.ini'),
                   ('server-T_Item.ini',OUT/'source/T_Item.ini'),('T_Item.ini',CLIENT/'T_Item.ini')):
    before=path.read_bytes()
    if label.endswith('T_Item.ini'):
        row=[str(ident),title,description,'']
    else:
        values=server if label=='S_Item.ini' else client
        row=values[61586].copy()
        row[0]=str(ident);row[1:7]=values[base][1:7]
        for column in (8,9,*range(32,39)):row[column]=values[base][column]
        row[7]=title;row[31]=description
        assert len(row)==67 and row[8]=='22' and row[13]=='130'
        assert row[39:49]==values[61586][39:49]
    after=before+(b'' if before.endswith(b'\n') else b'\r\n')+('|'.join(row)+'\r\n').encode('cp950')
    (OUT/label).write_bytes(after)
    files.append(dict(name=label,before=hashlib.sha256(before).hexdigest(),after=hashlib.sha256(after).hexdigest()))

spells=records(DATA/'S_Spell.ini')
valid=set(records(CLIENT/'C_Spell.ini'))
native=json.loads((ROOT/'docs/skill-masteries-native.json').read_text())
def mastery_rows(mask):
    return {i:r for i,r in spells.items() if len(r)>71 and r[28].isdigit() and 7<=int(r[28])<=12
            and (not r[33] or int(r[33])==0 or int(r[33])&mask)}
assert set(mastery_rows(131072))=={m['id'] for m in native},'Static schema must match earlier native capture'
assert all(m['max_order']==1 for m in native)
masteries=mastery_rows(32768)
assert len(masteries)==160 and set(masteries)<=valid
roads=records(DATA/'S_AdventureRoad.ini')
envoy=sorted({int(v) for r in roads.values() if r[1]=='16' for v in r[2:] if v.isdigit()})
assert len(envoy)==49 and set(envoy)<=set(spells)&valid
result=dict(item_id=ident,name=title,class_id=16,main_weapon_mask=32768,sub_weapon_mask=131072,
            item_type=22,base_model=base,envoy=envoy,
            masteries=[dict(id=i,type=int(r[28]),group=int(r[71]),rank=1) for i,r in masteries.items()],
            files=files,stats=server[61586][39:49],enchants=server[61586][21])
(OUT/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
(ROOT/'docs/guitar-switch-prepared.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(item_id=ident,name=title,envoy=len(envoy),mastery_tiers=len(masteries),enchants=result['enchants'])))
