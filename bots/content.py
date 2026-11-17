"""Read ordinary quest and scene data from the installed V15 tables.

`S_Mission.ini` is a pipe-delimited record table. The fields this module relies
on are:

     0  mission id            8  category (主線 / 支線 / ...)
     2  display title         9  accept NPC template (0 = virtual board)
     5  type flags           11  conditions (`If_*`, ';' inside one is OR)
     7  map that auto-starts 14  actions run on accept
                            15  objectives (`:'-separated')
                            16  return/turn-in NPC template
                            19  rewards

Objective arguments are `':'`-separated single-line commands. Every objective
kind is normalised to a short name (`kill`, `talk`, ...) so the drivers never
have to match authored spellings.
"""
from dataclasses import asdict, dataclass
import math
from pathlib import Path
import re
from wire import ProtocolError


KINDS = {
    'EquipItem': 'equip',
    'NPCTalk': 'talk',
    'NPCItem': 'use_item',
    'ItemGiven': 'deliver',
    'MonsterKilled': 'kill',
    'MonsterTreasureGot': 'collect_drop',
    'ItemGot': 'collect',
    'ItemCollect': 'collect',
    'AreaTravel': 'travel',
    'NewAreaTravel': 'travel',
    'CheckBuff': 'buff',
    'UseTimes': 'use_item',
    'PlayerLevel': 'level',
    'CombineAndMakingItem': 'craft',
}


@dataclass(frozen=True)
class Objective:
    kind: str
    args: tuple
    command: str


@dataclass(frozen=True)
class Condition:
    name: str
    args: tuple
    raw: str


@dataclass(frozen=True)
class Action:
    name: str
    args: tuple
    source: str
    raw: str


@dataclass(frozen=True)
class Reward:
    name: str
    args: tuple
    raw: str


@dataclass(frozen=True)
class Quest:
    id: int
    script: str
    title: str
    node: int
    flags: int
    category: str
    accept_npc: int
    return_npc: int
    conditions: tuple
    accept_actions: tuple
    objectives: tuple
    rewards: tuple
    display_items: tuple


def segments(script):
    """Split an authored command list; blank `####` slots are dropped."""
    return [part.strip('# \r\n\t') for part in script.split(':')
            if part.strip('# \r\n\t')]


def objectives(script):
    """Parse field 15. Unknown or non-numeric commands are kept as unsupported."""
    result = []
    for part in segments(script):
        words = part.split()
        if not words:
            continue
        if not all(re.fullmatch(r'-?\d+', word) for word in words[1:]):
            result.append(Objective('unsupported', (), words[0]))
            continue
        result.append(Objective(KINDS.get(words[0], 'unsupported'),
                                tuple(map(int, words[1:])), words[0]))
    return result


def conditions(script):
    result = []
    for part in segments(script):
        words = part.split()
        args = tuple(word for word in words[1:] if word != 'done')
        result.append(Condition(words[0], args, part))
    return result


def accept_actions(script):
    result = []
    for part in segments(script):
        words = part.split()
        source = 'MC' if words[0] == 'MC' else ''
        if source:
            words = words[1:]
        if not words:
            continue
        result.append(Action(words[0], tuple(words[1:]), source, part))
    return result


def rewards(script):
    result = []
    for part in segments(script):
        words = part.split()
        result.append(Reward(words[0], tuple(words[1:]), part))
    return result


def display_items(script):
    result = []
    for part in segments(script):
        words = part.split()
        if words and all(word.isdigit() for word in words):
            result.append(tuple(map(int, words)))
    return result


def _value(fields, index):
    return int(fields[index]) if fields[index].strip().lstrip('-').isdigit() else 0


def parse_quests(path):
    """Parse the whole mission table into `{id: Quest}`."""
    text = Path(path).read_bytes().decode('cp950', errors='surrogateescape')
    result = {}
    for record in re.split(r'(?m)(?=^\d+\|)', text)[1:]:
        fields = record.split('|')
        if len(fields) < 26:
            raise ProtocolError('Truncated quest table record')
        quest = Quest(
            id=_value(fields, 0), script=fields[1].strip(), title=fields[2].strip(),
            node=_value(fields, 7), flags=_value(fields, 5), category=fields[8].strip(),
            accept_npc=_value(fields, 9), return_npc=_value(fields, 16),
            conditions=tuple(conditions(fields[11])),
            accept_actions=tuple(accept_actions(fields[14])),
            objectives=tuple(objectives(fields[15])),
            rewards=tuple(rewards(fields[19])),
            display_items=tuple(display_items(fields[22])))
        if quest.id:
            result[quest.id] = quest
    return result


def quest_catalog(path):
    """JSON-friendly view used by the packaged lab assets."""
    return {quest.id: asdict(quest) for quest in parse_quests(path).values()}


class Scene:
    """Collision-adjacent scene data: spawns, travel areas, gateways, barriers."""

    def __init__(self, path):
        self.spawns, self.blocks, self.areas, self.gateways = {}, {}, {}, {}
        section = ''
        for line in Path(path).read_text(encoding='cp950', errors='surrogateescape').splitlines():
            if line.startswith('['):
                section = line.split(']')[0] + ']'
                continue
            values = [value.strip() for value in line.rstrip(',').split(',')]
            if section == '[event_area]' and len(values) >= 7 and values[0].isdigit():
                self.areas[int(values[0])] = (float(values[1]), float(values[2]), float(values[4]))
            if section == '[gateway_area]' and len(values) >= 3 and values[0].isdigit():
                # Columns: index, event_area, event, ..., trigger. The client
                # sends the *trigger* (column 7) to CheckNodeExit; the server
                # keys it as (node << 16) | trigger and rejects any other id.
                trigger = values[7] if len(values) > 7 and values[7].isdigit() else values[2]
                self.gateways[int(values[0])] = dict(area=int(values[1]),
                                                     event=int(values[2]),
                                                     trigger=int(trigger))
            if section == '[biology]' and len(values) >= 8 and values[0].isdigit():
                self.spawns[int(values[0])] = {
                    'template': int(values[1]),
                    'interaction': int(values[3]),
                    'position': (float(values[5]), float(values[6])),
                    'name': values[16] if len(values) > 16 else '',
                }
            if section == '[dynamic_block]' and len(values) >= 5 and values[0].isdigit():
                ident, left, right, bottom, top = map(int, values[:5])
                bits = values[5:]
                width, height = right - left, top - bottom
                if not 0 < width <= 4096 or not 0 < height <= 4096 or len(bits) != width * height or set(bits) - {'0','1'}:
                    raise ProtocolError('Invalid scene barrier dimensions')
                self.blocks[ident] = frozenset((left + i % width, bottom + i // width)
                                               for i, value in enumerate(bits) if value == '1')

    def positions(self, template):
        """Every authored spawn point for one biology template."""
        return [spawn['position'] for spawn in self.spawns.values()
                if spawn['template'] == template]

    def named(self, template):
        return [spawn for spawn in self.spawns.values() if spawn['template'] == template]

    def area(self, ident):
        return self.areas.get(ident)

    def active_obstacles(self, mobs):
        active = set()
        for ident, cells in self.blocks.items():
            spawn = self.spawns.get(ident)
            if not spawn:
                continue
            for mob in mobs.values():
                if mob['template'] == spawn['template'] and mob.get('alive', True):
                    x, y = spawn['position']
                    mx, my = mob['position']
                    if (x-mx)**2 + (y-my)**2 < 4:
                        active.update(cells)
                        break
        return active

    def live_barriers(self, mobs):
        """Block ids whose authored actor is still standing in the scene."""
        return {ident for ident, spawn in self.spawns.items()
                if ident in self.blocks
                for mob in mobs.values()
                if mob['template'] == spawn['template'] and mob.get('alive', True)
                and math.dist(mob['position'], spawn['position']) < 2}

    def inside_gateways(self, position):
        x, y = position
        return {ident for ident, gateway in self.gateways.items()
                if gateway['area'] in self.areas
                for ax, ay, radius in [self.areas[gateway['area']]]
                if (x-ax)**2 + (y-ay)**2 <= radius**2}
