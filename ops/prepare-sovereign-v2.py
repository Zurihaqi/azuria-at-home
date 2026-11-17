"""Build reversible V15-only template, level and missing-localization repairs."""
from pathlib import Path
import collections,hashlib,json,re
ROOT=Path(__file__).resolve().parent.parent
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db'
SOURCE=ROOT/'staging/pen-source'
OUT=ROOT/'staging/sovereign-v2';OUT.mkdir(exist_ok=True)
manifest={'required_level':130,'cap':150,'files':[],'translations':{},'items':[],'enchants':{},'sets':[]}
def decode(p):return p.read_bytes().decode('cp950',errors='surrogateescape')
def records(text):
 return {int(r[0]):r for c in re.split(r'(?m)(?=^\d+\|)',text)[1:] if len(r:=c.rstrip('\r\n').split('|'))>1}
texts={};sources={};pending=collections.defaultdict(dict)
def load(name):
 if name not in texts:
  p=(SOURCE if name.startswith('S_') else CLIENT)/name
  sources[name]=p;texts[name]=decode(p)
 return texts[name]
def replace(name,ident,row):
 load(name);pending[name][ident]=row
def effect(ident,name,desc,commands):
 row=['']*63;row[0]=str(ident);row[1]='WI0906';row[5]="Zrymund's "+name;row[6]='1';row[7]='0';row[47]='0';row[57]=desc
 for slot,(opcode,params) in zip([8,15,22,29],commands):
  assert len(params)<=6;row[slot]=str(opcode)
  row[slot+1:slot+1+len(params)]=[str(x) for x in params]
 for n in ['S_Enchant.ini','C_Enchant.ini']:replace(n,ident,row)
 replace('T_Enchant.ini',ident,[str(ident),row[5],desc,'','','',''])
 manifest['enchants'][str(ident)]={'name':row[5],'commands':commands}

effect(180001,'Sovereign Hunger','Physical and magical life steal 100%; CRIT DMG +500%; Move SPD +150%.',[(2021,[100,100]),(2022,[100,100]),(2043,[500]),(2051,[150])])
effect(180002,'Absolute Dominion','Damage +300%; damage taken -90%; PEN +999%; all elemental damage +300%.',[(2033,[300,300]),(2034,[-90,-90]),(2097,[999,0]),(2046,[300]*6)])
effect(180003,'Astral Breach','PEN +100%; Armor Piercing +100.',[(2097,[100,0]),(2155,[100,0])])
effect(180004,'Starbreaker Authority','Armor Piercing +500; maximum CRIT DMG +100%.',[(2155,[500,0]),(2096,[100])])
effect(180005,'Undying Constellation','Armor (2): Max HP +50%.',[(2085,[0,0,0,50,0,0])])
effect(180006,'Celestial Supremacy','Armor (5): PEN +200%; Armor Piercing +200; maximum CRIT DMG +50%.',[(2097,[200,0]),(2155,[200,0]),(2096,[50])])
effect(180007,'Cosmic Dominion','Accessories (3): damage +50%; CRIT DMG +200%; maximum CRIT DMG +50%; Armor Piercing +300.',[(2033,[50,50]),(2043,[200]),(2096,[50]),(2155,[300,0])])
effect(180008,'Infinite Singularity','Trophies (2): PEN +200%; Armor Piercing +300; healing potency +100%.',[(2097,[200,0]),(2155,[300,0]),(2091,[0,100])])

for name in ['S_Item.ini','C_Item.ini']:
 rows=records(load(name))
 for ident in range(61586,61597):
  row=rows[ident].copy();assert len(row)==67 and row[7].startswith("Zrymund's Astral Sovereign")
  row[13]='130';row[14]=''
  row[21]='180001;180002;180004' if ident==61586 else '180003'
  stats=[3000000 if ident==61586 else 500000,250000,250000,20000000 if ident==61588 else 5000000,500000,250000,75,75,50,100 if ident==61591 else 20 if ident==61586 else 0]
  row[39:49]=list(map(str,stats))
  row[31]='Requires SLv30. Astral Sovereign: armor 2/5-piece, accessories 3-piece, trophies 2-piece bonuses. '+('PEN +999%; Armor Piercing +500.' if ident==61586 else 'PEN +100%; Armor Piercing +100.')
  replace(name,ident,row)
  if name=='S_Item.ini':manifest['items'].append({'id':ident,'type':int(row[8]),'stats':stats,'level':130,'enchants':row[21]})
  if name=='C_Item.ini':replace('T_Item.ini',ident,[str(ident),row[7],row[31],''])
 # Set bonuses use hidden item templates, not direct enchant IDs.
 for ident,enchant in zip(range(61600,61604),range(180005,180009)):
  assert ident not in rows
  row=rows[37001].copy();assert row[8]=='61'
  row[0]=str(ident);row[7]=manifest['enchants'][str(enchant)]['name'];row[13]='1';row[21]=str(enchant)
  row[39:49]=['0']*10;row[31]='Astral Sovereign set bonus. Not an inventory item.'
  replace(name,ident,row)
  if name=='C_Item.ini':replace('T_Item.ini',ident,[str(ident),row[7],row[31],''])

set_specs=[(1001,'Astral Sovereign - Undying Constellation',{3:61587,4:61588,5:61589,6:61590,7:61591,18:61600,21:61601}),
 (1002,'Astral Sovereign - Cosmic Dominion',{8:61592,14:61593,15:61594,19:61602}),
 (1003,'Astral Sovereign - Infinite Singularity',{16:61596,17:61595,18:61603})]
for ident,title,fields in set_specs:
 row=['']*25;row[0]=str(ident);row[1]=title
 for field,value in fields.items():row[field]=str(value)
 for name in ['S_EquipSet.ini','C_EquipSet.ini']:
  assert ident not in records(load(name));replace(name,ident,row)
 replace('T_EquipSet.ini',ident,[str(ident),title,''])
 manifest['sets'].append({'id':ident,'name':title,'fields':fields})

for name in ['S_Parameter.ini','C_Parameter.ini']:
 row=records(load(name))[22];row[1]='150';replace(name,22,row)
# Preserve supported level formulas, align only client EXP columns to server.
levels=records(load('S_Level.ini'))
for ident,row in records(load('C_Level.ini')).items():
 if ident<=150 and ident in levels:
  row[1]=levels[ident][1];row[33]=levels[ident][33];replace('C_Level.ini',ident,row)

def missing(value):return not value.strip() or value.strip().lower() in ['err','error','(null)']
for kind,indices in [('Item',[7,31]),('ItemMall',[7,31]),('Biology',[5]),('Mission',[2,8,25]),('Title',[1,2,11,12])]:
 base=records(load('C_'+kind+'.ini'))
 name='T_'+kind+'.ini';translations=records(load(name));aliases=collections.defaultdict(set)
 for ident,row in translations.items():
  if ident in base and len(row)>1 and not missing(row[1]):aliases[base[ident][indices[0]]].add(row[1])
 stats=collections.Counter()
 for ident,native in base.items():
  original=translations.get(ident);row=original.copy() if original else [str(ident)]+['']*(len(indices)+1)
  if len(row)!=len(indices)+2:continue
  changed=False
  for dest,src in enumerate(indices,1):
   if not missing(row[dest]):continue
   candidate=native[src].strip() if len(native)>src else ''
   if dest==1:
    matches=aliases.get(candidate,set())
    if len(matches)==1:candidate=next(iter(matches));stats['english_alias']+=1
    elif candidate:stats['native_name']+=1
    else:candidate=f'Unused {kind} #{ident}';stats['unused_labels']+=1
   if candidate:row[dest]=candidate;changed=True
  if changed:replace(name,ident,row);stats['records_repaired']+=1
 manifest['translations'][kind]=dict(stats)

for name,text in texts.items():
 changes=pending[name].copy()
 def patch(match):
  ident=int(match[1]);row=changes.pop(ident,None)
  return '|'.join(row)+'\r\n' if row is not None else match[0]
 text=re.sub(r'(?ms)^(\d+)\|.*?(?=^\d+\||\Z)',patch,text)
 if changes:text=text.rstrip('\r\n')+'\r\n'+''.join('|'.join(row)+'\r\n' for row in changes.values())
 before=sources[name].read_bytes();after=text.encode('cp950',errors='surrogateescape')
 if before==after:continue
 (OUT/name).write_bytes(after)
 manifest['files'].append({'name':name,'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest(),'source':str(sources[name])})
(ROOT/'docs/sovereign-v2-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'files':len(manifest['files']),'translations':manifest['translations'],'gear_level':130,'cap':150},indent=2))
