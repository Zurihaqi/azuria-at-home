import gdb,json
obj=gdb.parse_and_eval('lapis::CSkyTowerFactory::Ins').dereference();out={'today_scene':int(obj['TodaySceneType']),'level_limit':int(obj['TowerLevelLimit'])}
def entries(mapping):
 tree=mapping['_M_t'];pt=tree.type.strip_typedefs().template_argument(1)
 def walk(node):
  if not int(node):return []
  pair=gdb.Value(int(node)+32).cast(pt.pointer()).dereference()
  return walk(node.dereference()['_M_left'])+[(int(pair['first']),pair['second'])]+walk(node.dereference()['_M_right'])
 return walk(tree['_M_impl']['_M_header']['_M_parent'])
out['states']={k:int(v) for k,v in entries(obj['OpenState'])}
rooms=[]
for ident,ptr in entries(obj['SkyTowers']):
 if ident not in [1,51,10001,10006,10011]:continue
 tower=ptr.dereference();row={'map_key':ident}
 for field in tower.type.fields():
  if field.name and field.type.strip_typedefs().code in [gdb.TYPE_CODE_INT,gdb.TYPE_CODE_ENUM,gdb.TYPE_CODE_BOOL,gdb.TYPE_CODE_CHAR]:row[field.name]=int(tower[field.name])
 rooms.append(row)
out['rooms']=rooms
print(json.dumps(out))
