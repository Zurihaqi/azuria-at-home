import gdb
exec(open('/root/verify-sovereign-v2.py').read().split('for typename')[0])
effect=lookup(zone['AllEffects'],40121)
for field in effect.type.fields():
 name=field.name
 if not name or not name.startswith('Command'):continue
 try:
  v=effect[name]['_M_impl'];start=v['_M_start'];count=int(v['_M_finish']-start)
  for i in range(count):
   ptr=(start+i).dereference();command=ptr.cast(ptr.dynamic_type).dereference();print(name,str(command))
 except gdb.error:pass
