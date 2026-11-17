"""Read-only learned-skill evidence; no account data or native packet dumps."""
import json
from pathlib import Path
from item_stream import equipment

for profile in ('pilot', 'arden'):
    path = Path('/var/lib/ak-bots') / profile / 'equipment.bin'
    _, data = equipment(path.read_bytes())
    count = data.number('h')
    assert 0 <= count <= 512
    skills = [(data.number('H'), data.number('B')) for _ in range(count)]
    slots = data.number('h')
    assert 0 <= slots <= 32
    values = [data.number('H') for _ in range(slots)]
    data.end()
    print(json.dumps(dict(profile=profile, learned_skills=skills, shortcut_slots=values)))
