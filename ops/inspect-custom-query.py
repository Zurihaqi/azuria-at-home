import gdb
obj=gdb.parse_and_eval('GameData::IGameData::m_pkInstance').cast(gdb.lookup_type('GameData::CGameData').pointer()).dereference()
for n in ['m_kItemQuery','m_kEnchantQuery']:
 q=obj[n]
 def fields(typ):
  for f in typ.strip_typedefs().fields():
   if f.is_base_class:fields(f.type)
   else:print(n,f.name,str(f.type))
 fields(q.type)
