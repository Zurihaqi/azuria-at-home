import gdb,json
obj=gdb.parse_and_eval('lapis::CSkyTowerManager::Ins').dereference();v=obj['m_vSkyTowerGroups']['_M_impl'];start=v['_M_start'];count=int(v['_M_finish']-start)
out=[]
for i in range(min(count,40)):
 group=(start+i).dereference();row={}
 a=group['GroupTowers']['_M_impl'];first=a['_M_start'];row['tower_count']=int(a['_M_finish']-first);row['first_tower']=int(first.dereference()) if row['tower_count'] else None
 for f in group.type.fields():
  if not f.name:continue
  value=group[f.name];t=value.type.strip_typedefs()
  if t.code in [gdb.TYPE_CODE_INT,gdb.TYPE_CODE_ENUM,gdb.TYPE_CODE_BOOL,gdb.TYPE_CODE_CHAR]:row[f.name]=int(value)
 out.append(row)
print(json.dumps({'group_count':count,'groups':out}))
tree=obj['GroupTypes']['_M_t'];pt=tree.type.strip_typedefs().template_argument(1)
def walk(node):
 if not int(node):return []
 pair=gdb.Value(int(node)+32).cast(pt.pointer()).dereference()
 return walk(node.dereference()['_M_left'])+[(int(pair['first']),int(pair['second']))]+walk(node.dereference()['_M_right'])
print('GROUP_TYPES',json.dumps(walk(tree['_M_impl']['_M_header']['_M_parent'])))
print('TODAY_SCENE',int(obj['TodaySceneType']),'LEVEL_LIMIT',int(obj['TowerLevelLimit']))
tree2=obj['m_mSkyTowers']['_M_t'];pairtype=tree2.type.strip_typedefs().template_argument(1)
def summarize(node):
 if not int(node):return []
 pair=gdb.Value(int(node)+32).cast(pairtype.pointer()).dereference();t=pair['second']
 row={k:int(t[k]) for k in ['ID','GroupID','ZoneID','Floor','Opened','TowerLevel','SceneType','FamilyID']}
 return summarize(node.dereference()['_M_left'])+[row]+summarize(node.dereference()['_M_right'])
rooms=summarize(tree2['_M_impl']['_M_header']['_M_parent']);summary={}
for room in rooms:
 key=str(room['GroupID'])
 if key not in summary:summary[key]={'count':0,'example':room}
 summary[key]['count']+=1
print('ROOMS',json.dumps(summary))
gdb.execute('ptype lapis::CSkyTowerManager::SSkyTowerGroup')
