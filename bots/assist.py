"""Select only fresh, visible hostile targets actually attacked by the leader."""
import math
import re
import struct
import time
from pathlib import Path


def templates_of_class(path, kind):
    text = Path(path).read_bytes().decode('cp950', errors='surrogateescape')
    return frozenset(int(row[0]) for block in re.split(r'(?m)(?=^\d+\|)', text)[1:]
                     if len(row := block.rstrip().split('|')) > 8 and row[6] == str(kind))


def hostile_templates(path):
    return templates_of_class(path, 2)


def resource_templates(path):
    return templates_of_class(path, 5)


class Assist:
    def __init__(self, hostile):
        self.hostile = frozenset(hostile)
        self.intent = None
        self.pending_query = None

    def query(self, leader, node, now=None):
        now = time.monotonic() if now is None else now
        if self.pending_query is not None and now - self.pending_query[2] < 2:
            return None
        self.pending_query = (leader, node, now)
        return struct.pack('<I', leader)

    def selected(self, payload, leader, node, now=None):
        """Correlate the native target-of-target reply with one leader query."""
        now = time.monotonic() if now is None else now
        pending = self.pending_query
        self.pending_query = None
        if pending is None or pending[:2] != (leader, node) or now - pending[2] >= 2:
            return
        if len(payload) != 9:
            return
        victim, kind, reserved = struct.unpack('<IBI', payload)
        if kind != 1 or reserved != 0:
            return
        self.intent = (leader, victim, now) if victim else None

    def observe(self, short, payload, leader, now=None):
        actor = victim = None
        if short == 'MeleeAttack' and len(payload) in (16, 18):
            actor, victim = struct.unpack_from('<II', payload)
        elif short in ('SpellCast', 'SpellHitToLife') and len(payload) == 24:
            _, actor, victim = struct.unpack_from('<HII', payload)
        if leader is not None and actor == leader:
            self.intent = (leader, victim, time.monotonic() if now is None else now)

    def target(self, party, combat, node, position, now=None):
        now = time.monotonic() if now is None else now
        if self.intent is None or position is None:
            return None
        leader, victim, when = self.intent
        destination = party.destination(now)
        if leader != party.leader or not any(m.id == leader for m in party.members.values()):
            return None
        if now - when >= 8 or destination is None or destination[0] != node:
            return None
        mob = combat.mobs.get(victim)
        if (mob is None or not mob.alive or mob.template not in self.hostile
                or any(m.id == victim for m in party.members.values())
                or not all(math.isfinite(v) for v in (*position, *mob.position, *destination[1:]))
                or math.dist(position, destination[1:]) > 30
                or math.dist(position, mob.position) > 30
                or math.dist(destination[1:], mob.position) > 30):
            return None
        return victim
