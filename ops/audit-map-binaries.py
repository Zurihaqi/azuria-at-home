from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent.parent
out={}
for name in ['client/Requiem Aurakingdom/game.bin','staging/v15-original/Aura Kingdom v15 Unpacked/game.bin']:
 data=(ROOT/name).read_bytes();out[name]={s:[i for i in range(len(data)) if False] for s in []}
 for s in ['S703','S741','s703','s741']:
  hits=[];start=0
  while (n:=data.find(s.encode(),start))>=0:hits.append(n);start=n+1
  out[name][s]=hits[:20]
print(json.dumps(out,indent=2))
