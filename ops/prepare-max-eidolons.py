"""Prepare build-supported, capped Eidolons without inventing skill ranks."""
from pathlib import Path
import hashlib,json,sys,runpy,struct
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'staging/max-eidolons';OUT.mkdir(exist_ok=True)
def table(path):
 raw=path.read_bytes();f=raw.decode('cp950','surrogateescape').split('|');n=int(f[2])
 return {int(r[0].strip()):r for i in range(3,len(f)-n,n) if (r:=f[i:i+n])[0].strip().isdigit()}
p=table(ROOT/'staging/live-S_Partner.ini')
client=table(ROOT/'client/Requiem Aurakingdom/data/db/C_Partner.ini')
grow=table(ROOT/'staging/max-eidolon-PartnerGrow.ini')
params=table(ROOT/'staging/max-eidolon-Parameter.ini')
skills=table(ROOT/'staging/ultimate/hxsy/Data/db/S_Spell.ini')
client_skills=table(ROOT/'client/Requiem Aurakingdom/data/db/C_Spell.ini')
rows=[]
caps={key:int(params[idx][1]) for key,idx in zip(
 ('emblem_attack','emblem_critical','emblem_recovery','emblem_maxhp','emblem_defence','emblem_dodge'),range(173,179))}
assert caps==dict(emblem_attack=3000,emblem_critical=1000,emblem_recovery=1000,emblem_maxhp=5000,emblem_defence=1000,emblem_dodge=1000)
affection=int(params[411][1]);assert affection==10
for ident,r in sorted(p.items()):
 if ident==1:continue # Tutorial-only Valkyrie; not a normal player Eidolon.
 assert ident in client
 spell_ids=[[int(v) for v in r[col].split(';') if v] for col in (59,60,61)]
 assert all(x and all(v in skills and v in client_skills for v in x) for x in spell_ids)
 ranks=[min(50,10*(len(x)-1)) for x in spell_ids]
 level=min(99,int(r[7]));assert level==99
 hp_grade=int(r[32]);assert 1<=hp_grade<=10
 hp=int(grow[level][30+hp_grade])+caps['emblem_maxhp']
 assert 0<hp<2147483647
 rows.append(dict(template_id=ident,level=level,evo_star=4,love_level=affection,love_exp=0,
                  loyalty_value=100,exp=0,hp=hp,spell_level1=ranks[0],spell_level2=ranks[1],spell_level3=ranks[2],**caps))
assert len(rows)==150 and len({r['template_id'] for r in rows})==150

# Validate prepared HP against the real native CKFElf::GetMaxHP code for every
# growth profile. Other derived combat stats are recalculated by the server.
sys.path.insert(0,str(ROOT/'ops/runtime'))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64
from unicorn.x86_const import UC_X86_REG_RDI,UC_X86_REG_RSP,UC_X86_REG_RAX
m=runpy.run_path(str(ROOT/'ops/disasm-binary.py'))
f,code,base,*_=m['load'](ROOT/'staging/ultimate/hxsy/ZoneServer/ZoneServer')
for row in rows:
 vm=Uc(UC_ARCH_X86,UC_MODE_64);vm.mem_map(0x9a1000,0x1000);vm.mem_map(0x100000,0x4000)
 vm.mem_write(0x9a1a00,code[0x9a1a00-base:0x9a1a00-base+55])
 vm.mem_write(0x1000c8,struct.pack('<H',4));vm.mem_write(0x100048,struct.pack('<QQ',0x101000,0x102000))
 vm.mem_write(0x1000d8,struct.pack('<i',caps['emblem_maxhp']))
 vm.mem_write(0x1010ae,struct.pack('<H',int(p[row['template_id']][32])))
 for grade in range(10):vm.mem_write(0x10207c+grade*4,struct.pack('<i',int(grow[99][31+grade])))
 vm.mem_write(0x103000,struct.pack('<Q',0x9a1a37));vm.reg_write(UC_X86_REG_RSP,0x103000);vm.reg_write(UC_X86_REG_RDI,0x100000)
 vm.emu_start(0x9a1a00,0x9a1a37,count=30)
 assert vm.reg_read(UC_X86_REG_RAX)==row['hp'],row['template_id']
manifest=dict(account_id=2419,character_id=50000001,excluded=[1],eidolons=rows,hp_native_tests=len(rows),
 sources={name:hashlib.sha256((ROOT/'staging'/src).read_bytes()).hexdigest() for name,src in
          (('S_Partner.ini','live-S_Partner.ini'),('S_Parameter.ini','max-eidolon-Parameter.ini'),('S_PartnerGrow.ini','max-eidolon-PartnerGrow.ini'))})
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(dict(eidolons=len(rows),hp_native_tests=len(rows),level=99,stars=4,affection=affection,skill_rank_patterns=sorted({tuple(r['spell_level'+str(i)] for i in range(1,4)) for r in rows}))))
