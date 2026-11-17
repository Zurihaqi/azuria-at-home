"""Resolve authored objective actors to maps and plan ordinary portal travel.

Quest tables name the actor (an NPC, monster or resource template), never the
map. Authored scene files are the authority on where a template is actually
placed and the portal graph is the authority on how an ordinary player walks
between those maps. This module joins the two so a quest driver can answer:

    * which map holds the actor for this objective?
    * which authored gateway sequence reaches it from here?

Nothing here invents progress or map access. The native server still admits or
rejects every gateway and remains the only authority on mission state.
"""
from pathlib import Path
import json

import portals

# Objective kinds whose first argument names a scene actor template. `collect`
# is excluded on purpose: ItemGot/ItemCollect name an item, not a spawn.
ACTOR_KINDS = frozenset({'kill', 'collect_drop', 'talk', 'deliver'})


def build_index(maps_dir):
    """Index every packaged scene as `template -> map -> spawn positions`."""
    from content import Scene
    templates, errors = {}, []
    for scene_path in sorted(Path(maps_dir).glob('S[0-9]*.ini')):
        stem = scene_path.stem[1:]
        if not stem.isdigit():
            continue
        node = int(stem)
        try:
            scene = Scene(scene_path)
        except Exception as error:  # a malformed scene must not hide other maps
            errors.append(dict(map=node, error=str(error)[:120]))
            continue
        for spawn in scene.spawns.values():
            positions = templates.setdefault(str(spawn['template']), {}).setdefault(str(node), [])
            x, y = spawn['position']
            positions.append([round(x, 3), round(y, 3)])
    return dict(version=1, templates=templates, errors=errors)


def write_index(maps_dir):
    index = build_index(maps_dir)
    target = Path(maps_dir) / 'world-index.json'
    target.write_text(json.dumps(index, separators=(',', ':')))
    target.chmod(0o644)
    return index


def load(path):
    """Load a packaged index, returning `None` when the asset is absent."""
    path = Path(path)
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    templates = {}
    for template, maps in raw.get('templates', {}).items():
        templates[str(template)] = {
            str(node): [tuple(position) for position in positions]
            for node, positions in maps.items()}
    return dict(version=raw.get('version', 1), templates=templates,
                errors=raw.get('errors', []))


def locations(index, template):
    """Maps that author a spawn for `template`, nearest data is chosen later."""
    if not index or template in (None, 0):
        return {}
    return index['templates'].get(str(template), {})


def objective_template(step, quest):
    """The scene actor a step needs, or `None` when the step is map-local.

    `use_item` only names an actor when the authored command is NPCItem. Timed
    potion/buff objectives (UseTimes/CheckBuff) stay on the current map.
    """
    kind = step.kind
    if kind in ACTOR_KINDS:
        return step.args[0] if step.args else None
    if kind == 'use_item':
        return (quest.return_npc or quest.accept_npc) if step.command == 'NPCItem' else None
    return None


def choose(index, template, start, graph, available, blocked, now=None):
    """Pick the reachable map holding `template`; prefer the current map.

    Returns `(node, route)` where route is the authored edge sequence, or
    `None` when no packaged map authors the template. A template that exists
    only on unreachable maps returns `None`; the caller reports unsupported
    content instead of pretending the actor is local.
    """
    maps = locations(index, template)
    if not maps:
        return None
    start = int(start)
    if str(start) in maps:
        return start, []
    best = None
    for raw_node in maps:
        if not raw_node.lstrip('-').isdigit():
            continue
        node = int(raw_node)
        if node not in available:
            continue
        route = portals.route(graph, start, node, available, blocked, now)
        if route is None:
            continue
        key = (len(route), node)
        if best is None or key < best[0]:
            best = (key, (node, route))
    return best[1] if best else None
