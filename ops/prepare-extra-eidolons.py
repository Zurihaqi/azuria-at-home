"""Port only the installed client's additional Eidolon dependency records.

Append missing records, retain every existing server row and custom change.
The generated payload must pass isolated native loading before deployment.
"""
from pathlib import Path
import hashlib,json,re,tarfile
ROOT=Path(__file__).resolve().parent.parent
BASE=ROOT/'staging/eidolon-port';SOURCE=BASE/'source';OUT=BASE/'payload';OUT.mkdir(exist_ok=True)
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db'
def read(path):
 raw=path.read_bytes();f=raw.decode('cp950','surrogateescape').split('|');n=int(f[2])
 rows={int(r[0].strip()):r for i in range(3,len(f)-n,n) if (r:=f[i:i+n])[0].strip().isdigit()}
 return raw,n,rows
def digest(raw):return hashlib.sha256(raw).hexdigest()
S={};C={};N={};RAW={};ADD={};files=[]
for path in SOURCE.glob('S_*.ini'):
 raw,n,rows=read(path);name=path.stem[2:];S[name]=rows;N[name]=n;RAW[name]=raw;ADD[name]={}
 cp=CLIENT/('C_'+name+'.ini')
 if cp.exists():
  _,cn,C[name]=read(cp);assert cn==n,(name,n,cn)
extra=sorted(C['Partner'].keys()-S['Partner'].keys());assert len(extra)==33
names=dict(zip(extra,('Aurora','Prometheus','Beelzebub','Guan Yu','Christmas Red Riding Hood',
 'Yagami Hime','New Year Anubis','Merlin','Samael','Cinderella','Wedding Inaba',
 'Summer Guan Yu','Cybele','Marie','Dionysus','Typhon','Christmas Frigga',
 'New Year Yagami Hime','Pan','Captain Hook','Zhou Yu','Maid Freya','Wedding Eris',
 'Summer Gaia','Zeus','Cao Cao','Peter Pan','Nunakawahime','Christmas Aoandon',
 'Rapunzel','New Year Pan','Okuninushi','Summer Cao Cao')))
def add(name,ident):
 ident=int(ident)
 if ident in S.get(name,{}):return
 assert ident in C[name],(name,ident)
 ADD[name][ident]=C[name][ident].copy()
for ident in extra:add('Partner',ident)
for name,col in (('PartnerCombo',2),('PartnerMission',1),('PartnerTalk',1),('EudemonRank',1)):
 for ident,r in C[name].items():
  if r[col].isdigit() and int(r[col]) in extra:add(name,ident)
assert len(ADD['PartnerCombo'])==660
spellset={int(v) for ident in extra for col in C['Partner'][ident][59:62] for v in col.split(';') if v}
for r in ADD['PartnerCombo'].values():
 for col in r[3:]:spellset.update(int(v) for v in col.split(';') if v.isdigit() and int(v) in C['Spell'])
effects=set()
for ident in extra:effects.update(int(v) for v in C['Partner'][ident][104:108] if v)
for r in ADD['EudemonRank'].values():
 for v in r[4:10]:
  if v.isdigit():
   if int(v) in C['Enchant']:effects.add(int(v))
   if int(v) in C['Spell']:spellset.add(int(v))
for ident in spellset:
 add('Spell',ident)
 effects.update(int(v) for v in re.findall(r'\d+',C['Spell'][ident][62]))
# Follow effect-to-effect and spell references in command parameters. Broad
# numeric matches can include valid extra dependencies but never replace rows.
todo=list(effects);seen=set()
while todo:
 ident=todo.pop()
 if ident in seen:continue
 seen.add(ident);r=C['Enchant'].get(ident,S['Enchant'].get(ident));assert r is not None,ident
 add('Enchant',ident)
 for col in (8,15,22,29,36):
  for p in r[col+1:col+7]:
   for v in p.split(';'):
    if not v.isdigit():continue
    val=int(v)
    if val>=60000 and val in C['Enchant'] and val not in seen:todo.append(val)
    if 30000<=val<60000 and val in C['Spell'] and val not in S['Spell'] and val not in ADD['Spell']:
     add('Spell',val)
     todo.extend(int(x) for x in re.findall(r'\d+',C['Spell'][val][62]))
# One newer opcode is absent in this engine: 2062(element,value). Its only
# referenced use is +10% damage against lightning targets. The native 2046
# six-element vector is equivalent; existing S_Enchant 35813 proves that form.
compat=[]
oldcodes={r[col] for r in S['Enchant'].values() for col in (8,15,22,29,36) if r[col]}
for ident,r in ADD['Enchant'].items():
 for col in (8,15,22,29,36):
  if r[col]=='2062':
   assert r[col+1:col+7]==['3','10','','','',''] and ident==151979
   proof=S['Enchant'][35813];assert proof[8:15]==['2046','','','10','','','']
   r[col:col+7]=proof[8:15]
   compat.append(dict(enchant=ident,old=2062,new=2046,proof=35813))
  assert not r[col] or r[col] in oldcodes,(ident,col,r[col])
# Keys, fragments and evolution/wish materials must also exist server-side.
itemids=set()
for ident in extra:
 p=C['Partner'][ident]
 itemids.update(int(p[i]) for i in range(35,59,2) if p[i].isdigit())
 if p[39]:itemids.add(int(p[39]))
for r in ADD['PartnerMission'].values():
 # Partner wishes contain up to three item/quantity pairs at 6,8,10.
 for col in (6,8,10):
  if r[col].isdigit() and (int(r[col]) in C['Item'] or int(r[col]) in C['ItemMall']):itemids.add(int(r[col]))
for ident in itemids:
 if ident in S['Item'] or ident in S['ItemMall']:continue
 add('ItemMall' if ident in C['ItemMall'] else 'Item',ident)
# The client key list and its fragment list are from different content dates.
# Create unambiguous new fragments/recipes rather than guessing key+1 IDs.
useditems=S['Item'].keys()|S['ItemMall'].keys()|C['Item'].keys()|C['ItemMall'].keys()
useditems=set(useditems);usedrecipes=set(S['Combine'])|set(C['Combine'])
fragment_map={};client_fragments={};client_recipes={}
for ident in extra:
 key=int(C['Partner'][ident][39]);assert int(C['ItemMall'][key][32])==ident
 frag=next(i for i in range(61605,65535) if i not in useditems);useditems.add(frag)
 recipe=next(i for i in range(27000,32000) if i not in usedrecipes);usedrecipes.add(recipe)
 r=C['ItemMall'][41895].copy();r[0]=str(frag);r[7]=names[ident]+' Key Fragment';r[32]=str(recipe)
 r[31]='A fragment of '+names[ident]+"'s key. Combine 10 fragments with 20 Medium Eidolon XP Crystals."
 ADD['ItemMall'][frag]=r;client_fragments[frag]=r;fragment_map[ident]=frag
 c=S['Combine'][2672].copy();c[0]=str(recipe);c[6]=str(key);c[7]=names[ident]+"'s Key";c[10]=str(frag);c[11]=r[7]
 ADD['Combine'][recipe]=c;client_recipes[recipe]=c
available=S['Item'].keys()|S['ItemMall'].keys()|ADD['Item'].keys()|ADD['ItemMall'].keys()
for ident in extra:
 p=C['Partner'][ident];gift_ids={int(v) for v in p[81:91] if v};assert len(gift_ids)==1
 for gift in gift_ids:
  assert gift not in S['DropItem']
  r=S['DropItem'][10113].copy();r[0]=str(gift);r[1]=p[4]
  frag=fragment_map[ident];assert frag in available
  ir=ADD['ItemMall'][frag];r[9]=str(frag);r[10]=ir[7]
  for col,val in ((25,15325),(29,11047)):
   r[col]=str(val);r[col+1]=S['Item'].get(val,S['ItemMall'].get(val))[7]
  assert sum(float(r[x] or 0) for x in range(12,129,4))==100
  ADD['DropItem'][gift]=r
# All ordinary combat/cooperative spell references resolve after appending.
assert all(int(v) in S['Spell'] or int(v) in ADD['Spell'] for id in extra for col in C['Partner'][id][59:62] for v in col.split(';') if v)
assert len(ADD['Spell'])==528
assets=[]
for ident in extra:
 for model in {C['Partner'][ident][i] for i in (2,92,93,94,95,96,97,98) if C['Partner'][ident][i]}:
  stem=model[:4].lower()
  for relative in (f'biology/model/{stem}.nif',f'biology/{stem}.kfm'):
   path=CLIENT.parents[1]/relative;assert path.is_file(),relative
   assets.append(dict(path=relative,sha256=digest(path.read_bytes())))
for name,entries in ADD.items():
 if not entries:continue
 raw=RAW[name];after=raw
 for ident,r in sorted(entries.items()):
  r=r.copy();r[0]=str(ident);assert len(r)==N[name],(name,ident,len(r),N[name])
  after+=(b'' if after.endswith(b'\n') else b'\r\n')+('|'.join(r)+'|\r\n').encode('cp950','surrogateescape')
 filename='S_'+name+'.ini';(OUT/filename).write_bytes(after)
 parsed=read(OUT/filename)[2];assert parsed.keys()==S[name].keys()|entries.keys()
 assert all([v.strip() for v in parsed[i]]==[v.strip() for v in r] for i,r in S[name].items())
 files.append(dict(name=filename,before=digest(raw),after=digest(after),added=len(entries)))
for name,entries in (('ItemMall',client_fragments),('Combine',client_recipes)):
 filename='C_'+name+'.ini';raw,cn,old=read(CLIENT/filename);after=raw
 assert cn==N[name]
 for ident,r in sorted(entries.items()):
  assert ident not in old
  after+=(b'' if after.endswith(b'\n') else b'\r\n')+('|'.join(r)+'|\r\n').encode('cp950','surrogateescape')
 dest=OUT/('client-'+filename);dest.write_bytes(after)
 assert len(read(dest)[2])==len(old)+len(entries)
 files.append(dict(name=filename,side='client',payload=dest.name,before=digest(raw),after=digest(after),added=len(entries)))
# Add localization only for absent IDs. Original Chinese descriptions are
# retained; main companion names use authored English display labels.
translations={
 'Partner':{i:[str(i),'Eidolon',names[i],C['Partner'][i][8]] for i in extra},
 'Spell':{i:[str(i),r[26],r[72],r[56],r[57],r[63]] for i,r in ADD['Spell'].items()},
 'Enchant':{i:[str(i),r[5],r[57],r[58],r[59],r[60]] for i,r in ADD['Enchant'].items()},
 'Item':{i:[str(i),r[7],r[31]] for kind in ('Item','ItemMall') for i,r in ADD[kind].items()},
 'EudemonRank':{i:[str(i),r[3]] for i,r in ADD['EudemonRank'].items()}}
for ident in extra:
 key=int(C['Partner'][ident][39]);translations['Item'][key]=[str(key),names[ident]+"'s Key",'Right-click to unlock '+names[ident]+'.']
for name,entries in translations.items():
 for side,directory in (('server',SOURCE),('client',CLIENT)):
  filename='T_'+name+'.ini';path=directory/filename
  raw=path.read_bytes();oldids={int(v) for v in re.findall(rb'(?m)^(\d+)\|',raw)}
  fresh={i:r for i,r in entries.items() if i not in oldids}
  if not fresh:continue
  after=raw
  # Translation files use a byte delimiter reader. CP950 Chinese characters
  # can contain 0x7c as a trail byte, unlike UTF-8; that corrupts column counts.
  # Keep the original file bytes intact and encode only appended translations
  # as UTF-8, with ASCII English companion names.
  for i,r in sorted(fresh.items()):
   if side=='client':
    # This client exits during startup when these new non-ASCII effect
    # translations are loaded. Keep new record IDs, but use safe English
    # labels until their full localized descriptions are verified.
    r=[value if value.isascii() else ('Eidolon effect '+str(i) if col==1 else '')
       for col,value in enumerate(r)]
   assert all('|' not in value for value in r)
   after+=(b'' if after.endswith(b'\n') else b'\r\n')+('|'.join(r)+'|\r\n').encode('utf8','surrogateescape')
  dest=OUT/(side+'-'+filename);dest.write_bytes(after)
  files.append(dict(name=filename,side=side,payload=dest.name,before=digest(raw),after=digest(after),added=len(fresh)))
manifest=dict(extra=extra,names=names,files=files,compatibility=compat,assets=assets,fragments=fragment_map,
 counts={k:len(v) for k,v in ADD.items() if v},language_note='Authored English companion names; original Chinese skill names/descriptions where no English translation is installed.',
 needs_native_lab=True)
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(BASE/'payload.tgz','w:gz') as archive:
 for path in OUT.iterdir():archive.add(path,arcname=path.name)
print(json.dumps({k:v for k,v in manifest.items() if k in ('extra','counts','compatibility')},indent=2))
