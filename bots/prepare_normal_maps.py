"""Package public normal-world navigation and authored portal links only."""
from pathlib import Path
import json
import re
import shutil
from navigation import Grid
from runtime import normal_config

normal_config()
source=Path('/root/hxsy/Data')
out=Path('/opt/ak-bot-prototype/maps')
out.mkdir(exist_ok=True)
manifest={}
portals={}
for scene in (source/'scene').glob('S*.ini'):
    match=re.fullmatch(r'S(\d+)\.ini',scene.name,re.I)
    if not match:continue
    node=int(match[1])
    section=''
    regions={};gates=[];events={};asset=None
    for line in scene.read_text(encoding='cp950',errors='surrogateescape').splitlines():
        if line.startswith('['):section=line.split(']')[0]+']';continue
        fields=line.rstrip(',').split(',')
        if section=='[globe_data]' and len(fields)>=5:asset=fields[4].strip()
        if section=='[event_area]' and len(fields)>=7 and fields[0].isdigit():
            regions[int(fields[0])]=[float(fields[1]),float(fields[2]),float(fields[4])]
        if section=='[gateway_area]' and len(fields)>=3 and all(x.isdigit() for x in fields[:3]):
            trigger=int(fields[7]) if len(fields)>7 and fields[7].isdigit() else int(fields[2])
            gates.append((int(fields[0]),int(fields[1]),int(fields[2]),trigger))
        if section=='[event]' and len(fields)>=4 and fields[0].isdigit():events[int(fields[0])]=fields[3]
    if not asset or not re.fullmatch(r'S\d+\.smp',asset,re.I) or not (source/'NodeMap'/asset).is_file():continue
    grid=Grid.read(source/'NodeMap'/asset)
    shutil.copy2(source/'NodeMap'/asset,out/asset)
    shutil.copy2(scene,out/scene.name)
    (out/asset).chmod(0o644);(out/scene.name).chmod(0o644)
    manifest[str(node)]=dict(asset=asset,width=grid.width,height=grid.height)
    def destination(event,seen=None):
        seen=set() if seen is None else seen
        if event in seen or len(seen)>5:return None
        seen.add(event);script=events.get(event,'')
        found=re.search(r'Event_Transport\s+(\d+)\s+(\d+)',script)
        if found:return tuple(map(int,found.groups()))
        for child in re.findall(r'Event_TriggerEvent\s+(\d+)',script):
            result=destination(int(child),seen)
            if result:return result
        return None
    links=[]
    for gate,area,event,trigger in gates:
        target=destination(event)
        if target and target[0]!=node and area in regions:
            links.append(dict(gate=gate,area=area,event=event,trigger=trigger,target=target[0],target_area=target[1],region=regions[area]))
    portals[str(node)]=links
(out/'manifest.json').write_text(json.dumps(manifest))
(out/'portals.json').write_text(json.dumps(portals))
import worldmap
index=worldmap.write_index(out)
print(f'Packaged {len(manifest)} public maps and {sum(map(len,portals.values()))} authored portal links, '
      f'indexed {len(index["templates"])} actor templates; no credentials/config files copied.')
