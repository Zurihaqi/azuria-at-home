import gdb,json
from pathlib import Path
obj=gdb.parse_and_eval('lapis::CZoneServer::Ins').dereference()
def lookup(mapping,wanted):
 tree=mapping['_M_t'];pt=tree.type.strip_typedefs().template_argument(1);node=tree['_M_impl']['_M_header']['_M_parent']
 while int(node):
  pair=gdb.Value(int(node)+32).cast(pt.pointer()).dereference();key=int(pair['first'])
  if key==wanted:return pair['second'].dereference()
  node=node.dereference()['_M_left' if wanted<key else '_M_right']
 return None
nodes=json.loads(Path('/root/envoy-node-candidates.json').read_text())
out=[]
for ident,count in nodes['counts'].items():
 ident=int(ident);p=lookup(obj['AllSpellMasters'],ident)
 if p is None:out.append({'id':ident,'missing':True});continue
 vec=p['SpellDatas'];start=vec['_M_impl']['_M_start'];end=vec['_M_impl']['_M_finish'];data=[]
 for i in range(int(end-start)):
  s=(start+i).dereference().dereference()
  data.append({'id':int(s['ID']),'type':int(s['Type']),'flags':int(s['Flag']),'weapon':int(s['WeaponType']),'level':int(s['Level']),'learn_limit':int(s['LearnLimit']),'class':int(s['Class'])})
 out.append({'id':ident,'occurrences':count,'ranks':data})
Path('/root/envoy-native-nodes.json').write_text(json.dumps(out,indent=2));print(json.dumps(out[:5],indent=2));print('templates',len(out),'missing',sum(x.get('missing',False) for x in out))
