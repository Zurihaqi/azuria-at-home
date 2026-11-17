import gdb,json
from pathlib import Path
manifest=json.loads(Path('/root/sovereign-v2-manifest.json').read_text())
obj=gdb.parse_and_eval('GameData::IGameData::m_pkInstance').cast(gdb.lookup_type('GameData::CGameData').pointer()).dereference()
def lookup(mapping,wanted):
 tree=mapping['_M_t'];pt=tree.type.strip_typedefs().template_argument(1);node=tree['_M_impl']['_M_header']['_M_parent']
 while int(node):
  pair=gdb.Value(int(node)+32).cast(pt.pointer()).dereference();key=int(pair['first'])
  if key==wanted:return pair['second'].dereference()
  node=node.dereference()['_M_left' if wanted<key else '_M_right']
 raise RuntimeError('Not loaded: '+str(wanted))
fields=['m_nAttack','m_nCritical','m_nRecover','m_nMaxHP','m_nDefence','m_nDodge','m_nCriticalDamage','m_nHitRate','m_nHealRate','m_nMoveSpeed']
for expected in manifest['items']:
 item=lookup(obj['m_kItemQuery']['m_kMap'],expected['id'])
 assert int(item['m_nRestrictLevel'])==130
 assert [int(item[n]) for n in fields]==expected['stats']
for ident in range(61600,61604):assert int(lookup(obj['m_kItemQuery']['m_kMap'],ident)['m_eItemType'])==61
for ident in range(180001,180009):lookup(obj['m_kEnchantQuery']['m_kMap'],ident)
zone=gdb.parse_and_eval('lapis::CZoneServer::Ins').dereference()
vectors={}
for field in zone.type.fields():
 if field.name and 'Exp' in field.name and 'vector' in str(field.type):
  try:
   value=zone[field.name];start=value['_M_impl']['_M_start'];size=int(value['_M_impl']['_M_finish']-start)
   vectors[field.name]=size
  except gdb.error:pass
assert vectors.get('AllLevelExp')==150,vectors
report={'items_verified':11,'hidden_bonus_items':4,'enchants_loaded':8,'level_vectors':vectors}
Path('/root/sovereign-v2-native.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
for typename in ['lapis::CEffectFactory','lapis::CItemFactory','lapis::CEC_AttrBloodNSunderArmor','lapis::CZoneServer','lapis::CFunctionSwitch']:
 try:gdb.execute('ptype '+typename)
 except gdb.error:pass
