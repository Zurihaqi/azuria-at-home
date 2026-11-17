"""Read-only inventory/equipment snapshot report; contains no account secrets."""
import json
from pathlib import Path
import re
from item_stream import inventory, equipment

text = Path('/root/hxsy/Data/db/S_Item.ini').read_bytes().decode('cp950', errors='replace')
rows = {int(r[0]): r for b in re.split(r'(?m)(?=^\d+\|)', text)[1:]
        if len(r := b.rstrip().split('|')) > 48}
for profile in ('pilot', 'arden'):
    state = Path('/var/lib/ak-bots') / profile
    report = {}
    for name, parser in (('inventory', inventory), ('equipment', equipment)):
        items, _ = parser((state / (name + '.bin')).read_bytes())
        report[name] = [dict(location=loc, id=item.id, type=rows.get(item.id, [''] * 49)[8],
                             level=rows.get(item.id, [''] * 49)[13],
                             stats=rows.get(item.id, [''] * 49)[39:49])
                        for loc, item in items.items() if item.id]
    print(json.dumps(dict(profile=profile, **report)))
