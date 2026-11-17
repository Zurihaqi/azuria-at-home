"""Restore known-working translations, retaining only narrowly scoped custom text."""
from pathlib import Path
import datetime,hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parent.parent
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db'
BASE=ROOT/'private/client-original/sovereign-v2-20261025T053956Z'
BACKUP=ROOT/'private/client-original'/('startup-recovery-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));BACKUP.mkdir()
custom={'T_Item.ini':set(range(61586,61597))|set(range(61600,61604)),
 'T_Enchant.ini':set(range(180001,180009))|set(range(180010,180020)),
 'T_EquipSet.ini':{1001,1002,1003}}
report={'backup':str(BACKUP),'restored':[]}
for source in BASE.glob('T_*.ini'):
 target=CLIENT/source.name;before=target.read_bytes();shutil.copy2(target,BACKUP/source.name)
 after=source.read_bytes()
 for ident in sorted(custom.get(source.name,set())):
  pattern=rb'(?m)^'+str(ident).encode()+rb'\|[^\r\n]*'
  matches=re.findall(pattern,before);assert len(matches)==1,(source.name,ident)
  row=matches[0];assert row.isascii(),(source.name,ident)
  if re.search(pattern,after):after,n=re.subn(pattern,lambda m:row,after);assert n==1
  else:after=after.rstrip(b'\r\n')+b'\r\n'+row+b'\r\n'
 with target.open('r+b') as out:out.write(after);out.truncate()
 report['restored'].append({'name':source.name,'sha256':hashlib.sha256(after).hexdigest(),'custom_rows':len(custom.get(source.name,set()))})
(ROOT/'docs/client-startup-recovery.json').write_text(json.dumps(report,indent=2))
print('Restored seven baseline translation tables; retained only custom item, effect and set names.')
