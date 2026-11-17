"""Test-only grant; refuses the host namespace and the production database."""
from pathlib import Path
import importlib.util,json,subprocess as sp
spec=importlib.util.spec_from_file_location('lab_guard','/root/ak-bot-explore/lab.py');lab=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab);lab.assert_inside()
def q(sql):
 r=sp.run(['runuser','-u','postgres','--','psql','-h','/run/postgresql','-X','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=sql,text=True,capture_output=True,cwd='/tmp',check=True);return r.stdout.strip()
def rows(sql):return json.loads(q("SELECT coalesce(json_agg(t),'[]') FROM ("+sql+")t"))
identity=json.loads(Path('/run/pilot/identity.json').read_text());char=json.loads(Path('/run/pilot/character.json').read_text())['id'];account=identity['account_id']
assert account==2421 and char!=50000001
before=rows(f'SELECT * FROM player_characters WHERE id={char}')[0];assert before['privilege']==0
Path('/var/lib/ak-bot-lab/snapshots/extra-eidolon-test-character-before.json').write_text(json.dumps(before))
def table(p):
 f=Path(p).read_bytes().decode('cp950','surrogateescape').split('|');n=int(f[2]);return {int(r[0].strip()):r for i in range(3,len(f)-n,n) if (r:=f[i:i+n])[0].strip().isdigit()}
p=table('/root/hxsy/Data/db/S_Partner.ini');g=table('/root/hxsy/Data/db/S_PartnerGrow.ini')
m=json.loads(Path('/run/extra-eidolon-manifest.json').read_text());eid=int(q('SELECT coalesce(max(elf_id),50000000) FROM elf'))+100
sql=['BEGIN;',f'DELETE FROM elf WHERE player_id={char};',f'UPDATE player_characters SET level=99,hp=50000,node_id=2,x=501.128,y=351.068,z=-5.67391,face_dir=0,quit=1,last_normal_area_id={(2<<16)|24},revive_area_id={(2<<16)|13} WHERE id={char} AND privilege=0;']
if 'eudemon_level' in before:sql.append(f'UPDATE player_characters SET eudemon_level=4 WHERE id={char};')
for index,ident in enumerate(m['extra']):
 r=p[ident];ranks=[min(50,(len(col.split(';'))-1)*10) for col in r[59:62]]
 hp=int(g[99][30+int(r[32])])+5000
 v=dict(elf_id=eid+index,loc=index if index<4 else index-4,player_id=char,account_id=account,template_id=ident,
        hp=hp,level=99,evo_star=4,love_level=10,love_exp=0,exp=0,loyalty_value=100,spell_state=29,
        spell_level1=ranks[0],spell_level2=ranks[1],spell_level3=ranks[2],emblem_attack=3000,emblem_critical=1000,
        emblem_recovery=1000,emblem_maxhp=5000,emblem_defence=1000,emblem_dodge=1000,background_id=1,skin_data=1,type=0 if index<4 else 1)
 sql.append('INSERT INTO elf ('+','.join(v)+') VALUES ('+','.join(map(str,v.values()))+');')
sql.append('COMMIT;');q('\n'.join(sql))
print(json.dumps(dict(isolated=True,ordinary_test_character=char,eidolons=33,active=4,storage=29)))
