import gdb,json
from pathlib import Path
obj=gdb.parse_and_eval('GameData::IGameData::m_pkInstance').cast(gdb.lookup_type('GameData::CGameData').pointer()).dereference()
def lookup(mapping,wanted):
 tree=mapping['_M_t'];pt=tree.type.strip_typedefs().template_argument(1);node=tree['_M_impl']['_M_header']['_M_parent']
 while int(node):
  pair=gdb.Value(int(node)+32).cast(pt.pointer()).dereference();key=int(pair['first'])
  if key==wanted:return pair['second'].dereference()
  node=node.dereference()['_M_left' if wanted<key else '_M_right']
 raise RuntimeError('Not loaded: '+str(wanted))
manifest=json.loads(Path('/root/zrymund-set.json').read_text())
fields={'attack':'m_nAttack','critical':'m_nCritical','recovery':'m_nRecover','max_hp':'m_nMaxHP','defence':'m_nDefence','dodge':'m_nDodge','critical_damage':'m_nCriticalDamage','hit_rate':'m_nHitRate','heal_rate':'m_nHealRate','move_speed':'m_nMoveSpeed'}
items=[]
for expected in manifest['items']:
 item=lookup(obj['m_kItemQuery']['m_kMap'],expected['id'])
 actual={name:int(item[field]) for name,field in fields.items()}
 assert actual==expected['stats'],(expected['id'],actual,expected['stats'])
 assert int(item['m_nRestrictLevel'])==1
 items.append({'id':expected['id'],'type':int(item['m_eItemType']),'quality':int(item['m_eItemQuality']),'level':1,'stats':actual})
enchants=[]
for ident in manifest['enchant_ids']:
 enchant=lookup(obj['m_kEnchantQuery']['m_kMap'],ident)
 enchants.append({'id':ident,'loaded':True})
report={'loaded_items':items,'loaded_enchants':enchants,'all_native_stats_match':True}
Path('/root/custom-set-live-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'items_verified':len(items),'enchants_loaded':len(enchants),'all_native_stats_match':True}))
