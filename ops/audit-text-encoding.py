from pathlib import Path
import json
out={}
for name in ['staging/server-T_Enchant-before.ini','client/Requiem Aurakingdom/data/db/T_Enchant.ini','client/Requiem Aurakingdom/data/db/T_Item.ini']:
 data=Path(name).read_bytes()
 try:data.decode('utf8');out[name]='valid UTF8'
 except UnicodeDecodeError as e:out[name]=str(e)
print(json.dumps(out))
