from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parent.parent
def rows(p):return {int(r[0]):r for c in re.split(r'(?m)(?=^\d+\|)',p.read_bytes().decode('cp950',errors='surrogateescape'))[1:] if len(r:=c.rstrip('\r\n').split('|'))>1}
client=ROOT/'client/Requiem Aurakingdom/data/db'
ench=rows(client/'C_Enchant.ini');text=rows(client/'T_Enchant.ini')
examples=[]
for ident,row in text.items():
 if len(row)<3 or ident not in ench:continue
 if 'reflect' in row[2].lower() and ('damage' in row[2].lower()):
  native=ench[ident]
  examples.append({'id':ident,'text':row[2][:320],'effects':[native[i:i+7] for i in [8,15,22,29]]})
print(json.dumps({'reflect_examples':examples[:12],'level_tail':{n:rows(client/'C_Level.ini')[n] for n in [148,149,150]}}))
