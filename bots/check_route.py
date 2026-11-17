"""Offline route diagnostic using public collision data, with no game connection."""
import json
from pathlib import Path
import time
from navigation import Grid
from wire import ProtocolError

root = Path('/opt/ak-bot-prototype/maps')
manifest = json.loads((root / 'manifest.json').read_text())
grid = Grid.read(root / manifest['2']['asset'])
for start, goal in [((288.25,297.25),(527.25,277.75))]:
    for limit in (50000, 200000):
        before = time.monotonic()
        try:
            route = grid.route(start, goal, max_expansions=limit)
            print(json.dumps(dict(limit=limit, seconds=round(time.monotonic()-before,2),
                                  waypoints=len(route), all_clear=all(grid.clear(grid.cell(*p)) for p in route))))
        except ProtocolError as error:
            print(json.dumps(dict(limit=limit, seconds=round(time.monotonic()-before,2), error=str(error))))
