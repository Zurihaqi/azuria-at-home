import gdb,json

def entries(mapping):
 tree=mapping['_M_t'];pair_type=tree.type.strip_typedefs().template_argument(1)
 def walk(node):
  if int(node)==0:return
  yield from walk(node.dereference()['_M_left'])
  pair=gdb.Value(int(node)+32).cast(pair_type.pointer()).dereference()
  yield pair['first'],pair['second']
  yield from walk(node.dereference()['_M_right'])
 yield from walk(tree['_M_impl']['_M_header']['_M_parent'])

groups={};total=0;bad=[]
for group,items in entries(gdb.parse_and_eval('lapis::CGlobalInfo::AllItemMallItem')):
 details={}
 for index,pointer in entries(items):
  item=pointer.dereference();note=item['Note']['_M_dataplus']['_M_p'].string()
  if note=='codex:supplies:v1':
   total+=1;detail=int(item['DetailType']);details[detail]=details.get(detail,0)+1
   if int(item['Point'])!=1 or int(item['SpecialPrice'])!=0:bad.append(int(item['ItemID']))
 if details:groups[int(group)]=details
report=dict(total=total,groups=groups,invalid_prices=bad)
assert total==1375 and not bad,report
with open('/root/supplies-cache-report.json','w') as out:json.dump(report,out,indent=2)
print(json.dumps(report,indent=2))
