import gdb,json
obj=gdb.parse_and_eval('lapis::CZoneServer::Ins').dereference()
out={}
for field in obj.type.fields():
 name=field.name
 if name and 'Exp' in name and 'vector' in str(field.type):
  value=obj[name]
  try:
   start=value['_M_impl']['_M_start'];end=value['_M_impl']['_M_finish'];size=int(end-start)
   out[name]={'size':size,'values':{i:int((start+i).dereference()) for i in [0,1,2,98,99,100] if i<size}}
  except Exception:out[name]={'type':str(field.type)}
print(json.dumps(out,indent=2))
with open('/root/level-exp-native.json','w') as stream:json.dump(out,stream,indent=2)
