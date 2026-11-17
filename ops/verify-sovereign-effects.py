import gdb,json
from pathlib import Path
exec(Path('/root/verify-sovereign-v2.py').read_text().split('for typename')[0])
for ident in range(1001,1004):
 value=lookup(zone['AllEquipSets'],ident)
 vector=value['AddAttrTable']['_M_impl'];start=vector['_M_start'];count=int(vector['_M_finish']-start)
 bonuses=[int((start+i).dereference()) for i in range(count)]
 print('SET',ident,bonuses)
 assert bonuses=={1001:[61600,0,0,61601,0,0],1002:[0,61602,0,0,0,0],1003:[61603,0,0,0,0,0]}[ident],bonuses
out={}
for ident in list(range(180001,180009))+list(range(180010,180020)):
 value=lookup(zone['AllEffects'],ident)
 commands=[]
 for field in ['CommandsStart','Commands','CommandsOnce','CommandsEnd','CommandsAttack','CommandsHit','CommandsHitFinal','CommandsBeAttacked','CommandsHurt','CommandsAbsorb','CommandsEnhance','CommandCondition']:
  vector=value[field]['_M_impl'];start=vector['_M_start'];count=int(vector['_M_finish']-start)
  for i in range(count):
   ptr=(start+i).dereference();command=ptr.cast(ptr.dynamic_type).dereference()
   attrs={}
   for name in ['SunderArmor','BloodArmor','Type','Value','Penetrate','Toughness']:
    try:attrs[name]=int(command[name])
    except gdb.error:pass
   commands.append({'event':field,'type':str(command.type),'values':attrs})
 out[ident]=commands
 print('EFFECT',ident,json.dumps(commands))
assert any(c['values'].get('SunderArmor')==500 for c in out[180004]),out[180004]
assert any(c['values'].get('Penetrate')==999 for c in out[180002]),out[180002]
for ident in range(180010,180020):
 assert any(c['values'].get('SunderArmor')==100 for c in out[ident]),ident
 assert any(c['values'].get('Penetrate')==100 for c in out[ident]),ident
Path('/root/sovereign-v2-effects.json').write_text(json.dumps(out,indent=2))
switch=gdb.parse_and_eval('lapis::CFunctionSwitch::pInstance').dereference()['FunctionSwitch']
tree=switch['_M_t'];pt=tree.type.strip_typedefs().template_argument(1);node=tree['_M_impl']['_M_header']['_M_parent']
while int(node):
 pair=gdb.Value(int(node)+32).cast(pt.pointer()).dereference();key=int(pair['first'])
 if key==1:print('LEVEL_SWITCH',str(pair['second']));break
 node=node.dereference()['_M_left' if 1<key else '_M_right']
