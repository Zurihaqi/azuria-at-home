from pathlib import Path
import collections,hashlib,json,re
root=Path(__file__).resolve().parent.parent
client=root/'client/Requiem Aurakingdom/data/db'
def read(path,fields=None):
 return {int(r[0]):r for chunk in re.split(r'(?m)(?=^[0-9]+\|)',path.read_bytes().decode('cp950',errors='strict'))[1:] if (len(r:=chunk.rstrip().split('|'))==fields if fields else len(r)>1)}
s={};c={}
for n in ['Item','ItemMall']:
 s.update(read(root/f'staging/ultimate/hxsy/Data/db/S_{n}.ini',67))
 c.update(read(client/f'C_{n}.ini',67))
catalog=json.loads((root/'docs/gear-catalog-expanded.json').read_text())
free=[i for i in range(61586,65535) if i not in s and i not in c]
definitions=[(24,'Starbreaker Whip'),(1,'Crown of Infinite Dawn'),(2,'Eventide Aegis'),(3,'Voidbinder Girdle'),(4,'Hands of Eternity'),(5,'Heavenstride Boots'),(6,'Mantle of the First Star'),(37,'Heart of the Cosmos'),(38,'Seal of Absolute Dominion'),(39,'Chronicle of Infinity'),(39,'Singularity Core')]
se=read(root/'staging/ultimate/hxsy/Data/db/S_Enchant.ini',63);ce=read(client/'C_Enchant.ini',63)
effect_ids=[i for i in range(180001,190000) if i not in se and i not in ce][:2]
assert len(effect_ids)==2
effect_specs=[
 ('Sovereign Hunger','100% life steal for physical and magical attacks; CRIT DMG +500%; Move SPD +150%.',[(2021,[100,100]),(2022,[100,100]),(2043,[500]),(2051,[150])]),
 ('Absolute Dominion','Damage dealt +200%; damage taken -90%; PEN +90%; damage of every element +200%.',[(2033,[200,200]),(2034,[-90,-90]),(2097,[90]),(2046,[200]*6)])]
enchant_rows=[];translations=[]
for eid,(title,desc,commands) in zip(effect_ids,effect_specs):
 row=['']*63;row[0]=str(eid);row[1]='WI0906';row[5]="Zrymund's "+title;row[6]='1';row[7]='0';row[47]='0';row[57]=desc
 for slot,(cmd,params) in zip([8,15,22,29],commands):
  row[slot]=str(cmd)
  for j,value in enumerate(params,slot+1):row[j]=str(value)
 enchant_rows.append(row);translations.append([str(eid),row[5],desc,'','','',''])
rows=[];item_trans=[];entries=[]
for ident,(typ,title) in zip(free,definitions):
 candidates=[r for r in catalog['items'] if r['type']==typ and r['id'] in s and r['id'] in c]
 base=max(candidates,key=lambda r:(r['required_level'],r['id']))['id']
 # Server/client rows must describe the same models and supported equipment slot.
 assert s[base][8]==c[base][8] and s[base][9]==c[base][9]
 row=s[base].copy();row[0]=str(ident);row[7]="Zrymund's Astral Sovereign - "+title
 row[10]='8';row[12]='-1';row[13]='1';row[14]='';row[15]='';row[16]='';row[17]='3'
 row[21]=';'.join(map(str,effect_ids)) if typ==24 else ''
 row[22]=row[23]=row[24]=row[25]=''
 row[28]='1'
 desc='Astral Sovereign set. Forged for Zrymund. Level 1 required. Extreme power with native V15 stat fields.'
 if typ==24:desc+=' Grants Sovereign Hunger and Absolute Dominion while equipped.'
 row[31]=desc
 stats={'attack':1000000 if typ==24 else 200000,'critical':50000,'recovery':50000,'max_hp':5000000 if typ==2 else 2000000,'defence':100000,'dodge':50000,'critical_damage':50,'hit_rate':50,'heal_rate':25,'move_speed':100 if typ==5 else 20 if typ==24 else 0}
 for index,value in enumerate(stats.values(),39):row[index]=str(value)
 assert len(row)==67 and all(abs(int(row[j]))<=65535 for j in range(45,49))
 rows.append(row);item_trans.append([str(ident),row[7],desc,''])
 entries.append({'id':ident,'base_id':base,'type':typ,'menu_type':90000,'required_level':1,'name':row[7],'stats':stats,'effects':effect_ids if typ==24 else []})
out=root/'staging/custom-set';out.mkdir(parents=True,exist_ok=True)
for name,records in [('items.ini',rows),('enchants.ini',enchant_rows),('item-text.ini',item_trans),('enchant-text.ini',translations)]:
 (out/name).write_bytes(('\r\n'.join('|'.join(r) for r in records)+'\r\n').encode('cp950'))
for name,fragment in [('C_Item.ini','items.ini'),('C_Enchant.ini','enchants.ini'),('T_Item.ini','item-text.ini'),('T_Enchant.ini','enchant-text.ini')]:
 path=client/name;backup=root/'private/client-original'/(name+'.pre-zrymund-set')
 if not backup.exists():backup.write_bytes(path.read_bytes())
 data=backup.read_bytes().rstrip(b'\r\n')+b'\r\n'+(out/fragment).read_bytes()
 path.chmod(0o666)
 with path.open('r+b') as f:f.write(data);f.truncate()
catalog['items']+=entries
(root/'docs/gear-catalog-custom.json').write_text(json.dumps(catalog,indent=2))
manifest={'name':"Zrymund's Astral Sovereign",'items':entries,'enchant_ids':effect_ids,'effects':effect_specs,'delivery':'Item Mall / AP / Gear Catalog / Zrymund Sovereign Set, 1 AP per item; no forced equip or quest change','validation':'Client/server templates constructed with valid field widths; server loader and in-game purchase test pending'}
(root/'docs/zrymund-set.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'items':len(entries),'ids':[x['id'] for x in entries],'effects':effect_ids},indent=2))
