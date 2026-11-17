"""Prepare only custom set rows; native PEN Init accepts -999..999 per effect."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'staging/pen-upgrade';OUT.mkdir(exist_ok=True)
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db'
SOURCES=ROOT/'staging/pen-source'
BONUS_ID=180003
DESC='Damage dealt +200%; damage taken -90%; PEN +999%; damage of every element +200%.'
BONUS_DESC='PEN +100% while equipped. Astral Sovereign armor, accessories and trophies each grant this bonus.'
manifest={'whip_pen_before':90,'whip_pen_after':999,'other_piece_pen':100,'other_pieces':10,'full_set_pen':1999,'enchant_id':BONUS_ID,'files':[]}

def sha(data):return hashlib.sha256(data).hexdigest()
def replace(text,ident,fields,change):
 pattern=r'(?m)^'+str(ident)+r'\|[^\r\n]*'
 def sub(match):
  row=match[0].split('|');assert len(row)==fields,(ident,len(row));change(row)
  return '|'.join(row)
 result,n=re.subn(pattern,sub,text);assert n==1,(ident,n)
 return result

for filename,source in [('S_Item.ini',SOURCES/'S_Item.ini'),('S_Enchant.ini',SOURCES/'S_Enchant.ini'),
                        ('C_Item.ini',CLIENT/'C_Item.ini'),('C_Enchant.ini',CLIENT/'C_Enchant.ini'),
                        ('T_Item.ini',CLIENT/'T_Item.ini'),('T_Enchant.ini',CLIENT/'T_Enchant.ini')]:
 before=source.read_bytes();text=before.decode('cp950',errors='surrogateescape')
 if filename in ['S_Item.ini','C_Item.ini']:
  for ident in range(61587,61597):
   def update(row):
    assert row[7].startswith("Zrymund's Astral Sovereign")
    assert row[21]=='','Unexpected existing custom passive'
    row[21]=str(BONUS_ID)
   text=replace(text,ident,67,update)
 elif filename in ['S_Enchant.ini','C_Enchant.ini']:
  def upgrade(row):
   assert row[22]=='2097' and row[23]=='90' and not row[24]
   row[23]='999';row[57]=DESC
  text=replace(text,180002,63,upgrade)
  assert not re.search(r'(?m)^180003\|',text)
  row=['']*63;row[0]=str(BONUS_ID);row[1]='WI0906';row[5]="Zrymund's Astral Breach";row[6]='1';row[7]='0';row[8]='2097';row[9]='100';row[47]='0';row[57]=BONUS_DESC
  text=text.rstrip('\r\n')+'\r\n'+'|'.join(row)+'\r\n'
 elif filename=='T_Item.ini':
  for ident in range(61587,61597):
   text=replace(text,ident,4,lambda row:row.__setitem__(2,row[2]+' PEN +100% while equipped.'))
 else:
  text=replace(text,180002,7,lambda row:row.__setitem__(2,DESC))
  assert not re.search(r'(?m)^180003\|',text)
  text=text.rstrip('\r\n')+'\r\n'+'|'.join([str(BONUS_ID),"Zrymund's Astral Breach",BONUS_DESC,'','','',''])+'\r\n'
 after=text.encode('cp950',errors='surrogateescape');(OUT/filename).write_bytes(after)
 # All unrelated raw record bytes remain exactly unchanged.
 def unrelated(data):
  result=data
  for ident in list(range(61587,61597))+[180002,180003]:
   result=re.sub(rb'(?m)^'+str(ident).encode()+rb'\|[^\r\n]*\r?\n?',b'',result)
  return result.rstrip(b'\r\n')
 assert unrelated(before)==unrelated(after),filename
 manifest['files'].append(dict(name=filename,before_sha256=sha(before),after_sha256=sha(after),source=str(source)))
(ROOT/'docs/set-pen-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({k:v for k,v in manifest.items() if k!='files'},indent=2))
