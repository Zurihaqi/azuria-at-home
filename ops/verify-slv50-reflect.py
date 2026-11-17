import gdb,json
from pathlib import Path
exec(Path('/root/verify-sovereign-v2.py').read_text().split('for typename')[0])
# The original 150-entry EXP vector and playable cap are deliberately retained.
level=lookup(obj['m_kLevelQuery']['m_kMap'],151)
print('NEXT_LEVEL_REFERENCE',str(level.type))
whip=lookup(obj['m_kItemQuery']['m_kMap'],61586)
effect=lookup(zone['AllEffects'],180020)
v=effect['CommandsAbsorb']['_M_impl'];start=v['_M_start'];count=int(v['_M_finish']-start);commands=[]
for i in range(count):
 ptr=(start+i).dereference();cmd=ptr.cast(ptr.dynamic_type).dereference()
 if 'CEC_DamageRebound' in str(cmd.type):commands.append({'type':str(cmd.type),'probability':int(cmd['Probability']),'reflect_percent':int(cmd['ReboundRate']),'damage_types':int(cmd['Type'])})
assert any(c['probability']==100 and c['reflect_percent']==100 for c in commands),commands
report={'reference_row_151_loaded':True,'exp_vector_size':vectors['AllLevelExp'],'reflection_commands':commands,'validation':'Native data loaded; player SLv50 retry pending'}
Path('/root/slv50-reflect-native.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
