from pathlib import Path
import collections,hashlib,json,re
ROOT=Path(__file__).resolve().parent.parent

def records(path,fields=None):
 out={}
 for chunk in re.split(r'(?m)(?=^\d+\|)',path.read_bytes().decode('cp950',errors='replace'))[1:]:
  row=chunk.rstrip('\r\n').split('|')
  if fields is None or len(row)==fields:out[int(row[0])]=row
 return out

missions=records(ROOT/'staging/S_Mission.ini',31)
quests=[]
for ident,row in missions.items():
 match=re.match(r'(?i)^lv\.?\s*(\d+)',row[2])
 level=int(match[1]) if match else 70 if row[8]=='冒險故事' else None
 if row[8] in ['主線','支線','冒險故事','小屋莊園任務'] and level is not None and level<=99 and ident not in [2523,2524]:
  quests.append(dict(id=ident,title=row[2],category=row[8],level=level))
assert len(quests)==1323 and all(not q['title'].startswith('SLv') for q in quests)

server={};client={};names={}
for name in ['Item','ItemMall']:
 server.update(records(ROOT/f'staging/ultimate/hxsy/Data/db/S_{name}.ini',67))
 client.update(records(ROOT/f'client/Requiem Aurakingdom/data/db/C_{name}.ini',67))
 names.update(records(ROOT/f'client/Requiem Aurakingdom/data/db/T_{name}.ini'))

groups={name:[] for name in ['eidolon_growth','fortification','enchantment_cards','forging']}
for ident,row in sorted(server.items()):
 other=client.get(ident);text=names.get(ident,['','']);title=text[1].strip() if len(text)>1 else ''
 typ=int(row[8]) if row[8].isdigit() else -1
 if not title or not other or row[8]!=other[8] or row[1]!=other[1] or not row[1] or not 1<=ident<=65535:continue
 if re.search(r'(?i)\btest\b|undefined|reserved|occupied|japanese|dev only|do not use|\[gm\]',title):continue
 tag=None
 # These native types are EXP crystals, Eidolon accessories/crests and purification scrolls.
 if typ in [69,71,73,83] or (typ==57 and re.search(r'(?i)evolutionary bead|eidolon.*(?:upgrade|evol|star|emblem|wish|stardust)|(?:upgrade|evol).*eidolon',title)):
  tag='eidolon_growth'
 elif typ==60 and re.search(r'(?i)fortif|enhancement',title):tag='fortification'
 elif typ in [63,64] and re.search(r'(?i)enchant.*card|card.*enchant',title):tag='enchantment_cards'
 elif typ in [58,65,66,67,102] or (typ==57 and re.search(r'(?i)forg|refin|alloy|\bore\b|ingot|crafting|\bcore\b',title)):
  tag='forging'
 if tag:groups[tag].append(dict(id=ident,type=typ,name=title))

locations={'eidolon_growth':(3,1,'Eidolons → Eidolons'),'fortification':(5,1,'Gear Improvement → Fortification'),
           'enchantment_cards':(2,6,'Costumes → Enchantment Cards'),'forging':(5,3,'Gear Improvement → Other')}
for name,items in groups.items():
 for item in items:item.update(item_group=locations[name][0],detail_type=locations[name][1],section=name)
out=dict(character_id=50000001,account_id=2419,level=99,exp=1002435749,exp_next_level=1002435750,
         quests=quests,quest_counts=dict(collections.Counter(x['category'] for x in quests)),awakening_quest=2523,awakening_state=3,
         excluded_awakening_completion=[2523,2524],feature_bits=15,
         supplies=[i for group in groups.values() for i in group],supply_counts={k:len(v) for k,v in groups.items()},
         locations={k:v[2] for k,v in locations.items()},price_ap=1,
         quest_source_sha256=hashlib.sha256((ROOT/'staging/S_Mission.ini').read_bytes()).hexdigest())
(ROOT/'docs/lv99-supplies-manifest.json').write_text(json.dumps(out,indent=2))
print(json.dumps(dict(quests=len(quests),quest_counts=out['quest_counts'],supplies=out['supply_counts'],exp=out['exp']),indent=2))
