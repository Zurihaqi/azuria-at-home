import gdb,json
from pathlib import Path
obj=gdb.parse_and_eval('lapis::CZoneServer::Ins').dereference()
valid=set(json.loads(Path('/root/client-spell-ids.json').read_text()))
def entries(mapping):
 tree=mapping['_M_t'];pt=tree.type.strip_typedefs().template_argument(1)
 def walk(node):
  if not int(node):return
  yield from walk(node.dereference()['_M_left'])
  p=gdb.Value(int(node)+32).cast(pt.pointer()).dereference();yield int(p['first']),p['second'].dereference()
  yield from walk(node.dereference()['_M_right'])
 yield from walk(tree['_M_impl']['_M_header']['_M_parent'])
result=[]
for ident,master in entries(obj['AllSpellMasters']):
 vec=master['SpellDatas'];start=vec['_M_impl']['_M_start'];end=vec['_M_impl']['_M_finish'];n=int(end-start)
 if not n:continue
 first=start.dereference().dereference();typ=int(first['Type']);weapon=int(first['WeaponType'])
 if not (7<=typ<=12) or weapon and not weapon&131072:continue
 ranks=[]
 for j in range(n):
  spell=(start+j).dereference().dereference();sid=int(spell['ID'])
  if sid not in valid:break
  ranks.append(sid)
 if not ranks:continue
 result.append({'id':ident,'type':typ,'weapon':weapon,'group':int(first['SpellGroup']),'name':first['Name']['_M_dataplus']['_M_p'].string(),'max_order':len(ranks),'spell_ids':ranks})
Path('/root/skill-masteries-native.json').write_text(json.dumps(result,indent=2));print('Applicable skill mastery choices:',len(result));print(json.dumps(result[:4],indent=2))
