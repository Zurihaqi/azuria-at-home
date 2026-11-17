from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parent.parent
def records(path):return {int(r[0]):r for c in re.split(r'(?m)(?=^\d+\|)',path.read_bytes().decode('cp950',errors='surrogateescape'))[1:] if len(r:=c.rstrip('\r\n').split('|'))>1}
server=records(ROOT/'staging/live-S_Node.ini');client=records(ROOT/'client/Requiem Aurakingdom/data/db/C_Node.ini');out={}
for ident in [701,702,703,704,741]:
 s=server[ident];c=client[ident]
 out[ident]={'server_len':len(s),'client_len':len(c),'differences':[(i,a,b) for i,(a,b) in enumerate(zip(s,c)) if a!=b],'server_fields':{i:v for i,v in enumerate(s) if v and i not in [1,3]}}
print(json.dumps(out,indent=2))
