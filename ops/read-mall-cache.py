# Executed by gdb's embedded Python; reads memory only, calls no inferior functions.
import gdb,json
def entries(mapping):
    tree=mapping['_M_t']
    pair_type=tree.type.strip_typedefs().template_argument(1)
    def walk(node):
        if int(node)==0:return
        yield from walk(node.dereference()['_M_left'])
        pair=gdb.Value(int(node)+32).cast(pair_type.pointer()).dereference()
        yield pair['first'],pair['second']
        yield from walk(node.dereference()['_M_right'])
    yield from walk(tree['_M_impl']['_M_header']['_M_parent'])
report=[]
for group,items in entries(gdb.parse_and_eval('lapis::CGlobalInfo::AllItemMallItem')):
    count=0;new=0;examples=[];details={};bad_prices=0
    for index,pointer in entries(items):
        count+=1
        item=pointer.dereference()
        note=item['Note']['_M_dataplus']['_M_p'].string()
        if note.startswith('codex:gear-catalog'):
            new+=1
            detail=int(item['DetailType'])
            details[detail]=details.get(detail,0)+1
            if int(item['Point'])!=1 or int(item['SpecialPrice'])!=0:bad_prices+=1
            if len(examples)<3:examples.append({'index':int(index),'id':int(item['ItemID']),'detail':int(item['DetailType'])})
    report.append({'group':int(group),'cached_items':count,'catalog_items':new,'catalog_detail_counts':details,'invalid_catalog_prices':bad_prices,'samples':examples})
print(json.dumps(report,indent=2))
with open('/root/mall-cache-report.json','w') as out:json.dump(report,out,indent=2)
