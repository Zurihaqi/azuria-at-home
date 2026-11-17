"""Package only public collision assets, never server configs or credentials."""
import hashlib
import json
from pathlib import Path
import re
import shutil
from lab import assert_inside
from navigation import Grid
assert_inside()
destination = Path('/opt/ak-bot-prototype/maps')
destination.mkdir(mode=0o755, exist_ok=True)
manifest = {}
for node in (1, 2, 3, 4, 201, 610):
    scene = Path('/root/hxsy/Data/scene', f'S{node:03}.ini')
    rows = scene.read_text(encoding='cp950', errors='surrogateescape').splitlines()
    header = next(i for i,row in enumerate(rows) if row.strip().startswith('[globe_data]'))
    fields = rows[header + 1].split(',')
    asset = fields[4].strip()
    if not re.fullmatch(r'S\d{3}\.smp', asset, re.I):
        raise SystemExit('Unexpected collision asset name')
    source = Path('/root/hxsy/Data/NodeMap', asset)
    grid = Grid.read(source)
    target = destination / asset
    shutil.copyfile(source, target)
    target.chmod(0o644)
    scene_target = destination / scene.name
    shutil.copyfile(scene, scene_target)
    scene_target.chmod(0o644)
    manifest[str(node)] = {'asset': asset, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                           'width': grid.width, 'height': grid.height}
(destination / 'manifest.json').write_text(json.dumps(manifest, indent=2))
mission_source = Path('/root/hxsy/Data/db/S_Mission.ini')
mission_target = destination / 'S_Mission.ini'
shutil.copyfile(mission_source, mission_target)
mission_target.chmod(0o644)
print('Packaged six verified collision maps, the starter tutorial, and the quest table.')
