from pathlib import Path
import json,re
root=Path(__file__).resolve().parent.parent
def read(path):
 return {int(r[0]):r for chunk in re.split(r'(?m)(?=^[0-9]+\|)',path.read_bytes().decode('cp950',errors='replace'))[1:] if len(r:=chunk.rstrip().split('|'))>1}
out={}
for name,key in [('Title','titles'),('Panel','panels')]:
 server=read(root/f'staging/ultimate/hxsy/Data/db/S_{name}.ini')
 client=read(root/f'client/Requiem Aurakingdom/data/db/C_{name}.ini')
 out[key]=sorted(server.keys()&client.keys())
server=read(root/'staging/ultimate/hxsy/Data/db/S_Achievement.ini')
client=read(root/'client/Requiem Aurakingdom/data/db/C_Achievement.ini')
out['medals']=[{'id':i,'required':int(row[11] or 1),'point':int(row[15] or 0),'group':int(row[31]),'rank':int(row[32])}
 for i,row in server.items() if i in client and len(row)==39 and row[29].startswith('Badge') and row[31].isdigit() and int(row[31])>0]
out['envoy_points']=1000
(root/'docs/unlock-manifest.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in out.items()},indent=2))
