"""Client-only icons and Samael text; never modifies native gameplay effects."""
from pathlib import Path
import datetime,hashlib,json,re,shutil,subprocess
ROOT=Path(__file__).resolve().parent.parent; DB=ROOT/'client/Requiem Aurakingdom/data/db'
check=subprocess.run(['powershell','-NoProfile','-Command',
    "@(Get-Process Game,game.bin,Launcher -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,check=True)
assert check.stdout.strip()=='0','Close the game first'
def table(path):
    f=path.read_bytes().decode('cp950','surrogateescape').split('|');n=int(f[2])
    return {int(r[0].strip()):r for i in range(3,len(f)-n,n) if (r:=f[i:i+n])[0].strip().isdigit()}
e=table(DB/'C_Enchant.ini');p=table(DB/'C_Partner.ini')
new=table(ROOT/'staging/eidolon-port/payload/S_Enchant.ini')
old=table(ROOT/'staging/eidolon-port/source/S_Enchant.ini')
m=json.loads((ROOT/'staging/eidolon-port/payload/manifest.json').read_text())
needed=set(new)-set(old)
for ident in m['extra']:
    needed.update(int(v) for v in p[ident][99:108] if v.isdigit() and int(v) in e)
todo=list(needed)
while todo:
    r=e[todo.pop()]
    for col in (8,15,22,29):
        if r[col] in ('1082','1084','1085','1086'):
            for value in r[col+1:col+7]:
                if value.isdigit() and int(value) in e and int(value) not in needed:
                    needed.add(int(value));todo.append(int(value))
# These shared star passives appeared repeatedly in the actual noPhoto log.
needed.update((51006,54786,54799,54814,54827))
icons={i for i in needed if not e[i][1]}
assert (DB.parents[1]/'ui/skillicon/E60005.dds').is_file()
backup=ROOT/'private/client-original'/('eidolon-presentation-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir()
files=('C_Enchant.ini','T_Enchant.ini','T_Spell.ini')
for name in files:shutil.copy2(DB/name,backup/name)
raw=(DB/'C_Enchant.ini').read_bytes()
for ident in sorted(icons):
    pattern=rb'(?m)^('+str(ident).encode()+rb'\|)\|'
    raw,n=re.subn(pattern,lambda match:match[1]+b'E60005|',raw);assert n==1,ident
after=table_data=raw
# Verify the only C_Enchant fields changed are formerly blank icon references.
temp=backup/'patched-C_Enchant.ini';temp.write_bytes(raw);parsed=table(temp)
assert set(parsed)==set(e)
for ident,row in e.items():
    assert parsed[ident][2:]==row[2:]
    assert parsed[ident][1]==('E60005' if ident in icons else row[1])

def replace_rows(raw,values):
    for ident,fields in sorted(values.items()):
        line=(str(ident)+'|'+'|'.join(fields)+'|\r\n').encode('ascii')
        pattern=rb'(?ms)^'+str(ident).encode()+rb'\|.*?(?=^\d+\||\Z)'
        if re.search(pattern,raw):raw,n=re.subn(pattern,lambda match:line,raw);assert n==1
        else:raw=raw.rstrip(b'\r\n')+b'\r\n'+line
    return raw

buffs={}
def buff(ident,name,desc):buffs[ident]=[name,desc,'','','']
for ident in (150363,*range(150372,150377)):
    reduction=abs(int(e[ident][20]));buff(ident,'Dark Crystal Slash',f'Silenced; DEF -{reduction}%.')
for ident in range(150377,150382):buff(ident,'Dark Crystal Slash',f'Dark damage received +{e[ident][14]}%.')
for ident in range(150382,150387):buff(ident,'Dark Crystal Slash',f'Tenacity -{abs(int(e[ident][10]))}%.')
for ident in (150364,*range(150387,150392)):
    amount=abs(int(e[ident][9]));buff(ident,'Dark Wing Strike',f'Takes damage over time: #B5${amount}#.')
for ident in range(150392,150397):
    buff(ident,'Dark Wing Strike',f'Dark skill damage +{e[ident][10]}%; CRIT chance +{int(e[ident][16])/10:g}%.')
for ident in range(150397,150400):buff(ident,'Dark Wing Strike',f'Accuracy +{e[ident][9]}%.')
buff(150365,'Dark Feather Seal','Movement speed +20%.')
for ident,name,desc in ((54786,'Onslaught I','DMG +8%.'),(54814,'Onslaught II','DMG +16%.'),
                        (54799,'Shadowwalker I','Dark skill damage +15%.'),(54827,'Shadowwalker II','Dark skill damage +30%.'),
                        (51006,'Silence','Cannot use skills.')):buff(ident,name,desc)
spells={}
for index,column in enumerate(p[253][59:62]):
    for ident in map(int,column.split(';')):
        name=('Dark Crystal Slash','Dark Wing Strike','Dark Feather Seal')[index]
        desc=('Samael strikes the target, silencing it and reducing its DEF.',
              'Samael strikes with dark wings, inflicting damage over time.',
              'Samael blesses nearby allies, increasing movement speed by 20%.')[index]
        # T_Spell: ID, name, description, two calculated display fields, final field.
        source=(DB/'T_Spell.ini').read_bytes();match=re.search(rb'(?ms)^'+str(ident).encode()+rb'\|.*?(?=^\d+\||\Z)',source)
        if match:
            fields=match[0].rstrip(b'\r\n').split(b'|');assert len(fields)==7,(ident,len(fields))
            tail=[v.decode('ascii','ignore') for v in fields[3:6]]
        else:tail=['','','']
        spells[ident]=[name,desc,*tail]
translations=replace_rows((DB/'T_Enchant.ini').read_bytes(),buffs)
spelltext=replace_rows((DB/'T_Spell.ini').read_bytes(),spells)
try:
    (DB/'C_Enchant.ini').write_bytes(after)
    (DB/'T_Enchant.ini').write_bytes(translations)
    (DB/'T_Spell.ini').write_bytes(spelltext)
except BaseException:
    for name in files:shutil.copy2(backup/name,DB/name)
    raise
report=dict(backup=str(backup),icons_fixed=sorted(icons),samael_buff_texts=len(buffs),samael_skill_texts=len(spells),gameplay_unchanged=True,
            hashes={name:hashlib.sha256((DB/name).read_bytes()).hexdigest() for name in files})
(ROOT/'docs/eidolon-presentation-repair.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
