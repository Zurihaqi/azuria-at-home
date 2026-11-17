"""Use the matching V15 default player-card atlas, preserving a rollback copy."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import zlib
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / 'client/Requiem Aurakingdom'
ATLAS = CLIENT / 'uidata/imagesets'


def main():
    manifest = json.loads((ROOT / 'docs/v15-original-archive.json').read_text())
    expected = {entry['name'].split('/', 1)[1].lower(): entry
                for entry in manifest['files']}
    target = ATLAS / 'main.imageset'
    original = target.read_bytes()
    texture = ATLAS / 'main.dds'
    data = texture.read_bytes()
    reference = expected['uidata/imagesets/main.dds']
    assert len(data) == reference['size']
    assert f'{zlib.crc32(data):08x}' == reference['crc']
    layout = ET.fromstring(original)
    assert layout.get('Imagefile') in ('main.png', 'main.dds')
    with Image.open(texture) as image:
        width, height = image.size
        assert image.mode == 'RGBA', 'Preserve the original alpha channel'
        outside = [region.get('Name') for region in layout
                   if int(region.get('XPos')) + int(region.get('Width')) > width
                   or int(region.get('YPos')) + int(region.get('Height')) > height]
        # The supplied V15 imageset already has a malformed, unrelated Coin7 row.
        # Preserve every definition; validate the card regions used by this change.
        for name in ('PlayerInfo', 'TargetInfoP', 'TargetInfoM', 'TargetInfoPH'):
            assert name not in outside
    updated = original.replace(b'Imagefile="main.png"', b'Imagefile="main.dds"')
    parsed = ET.fromstring(updated)
    assert parsed.get('Imagefile') == 'main.dds'
    assert [x.attrib for x in parsed] == [x.attrib for x in layout]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT / 'private/client-original' / ('default-player-card-' + stamp)
    backup.mkdir()
    shutil.copy2(target, backup / target.name)
    shutil.copy2(ATLAS / 'main.png', backup / 'main.png')
    target.write_bytes(updated)
    assert target.read_bytes() == updated
    report = dict(
        client=str(CLIENT), backup=str(backup),
        change='main.imageset now loads the original V15 main.dds atlas',
        source='Matching V15 archive manifest; existing local DDS verified by size and CRC32',
        texture_crc32=reference['crc'],
        texture_sha256=hashlib.sha256(data).hexdigest(),
        imageset_before_sha256=hashlib.sha256(original).hexdigest(),
        imageset_after_sha256=hashlib.sha256(updated).hexdigest(),
        region_count=len(layout), dimensions=[width, height],
        validation='XML parsed; all region names/coordinates preserved; card regions inside texture bounds; original RGBA retained',
        existing_outside_regions_preserved=outside,
        gameplay_changed=False, restart_client_required=True,
        in_game_confirmation='pending')
    (ROOT / 'docs/default-player-card-restore.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
