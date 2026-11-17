"""Avoid explicitly supported native boss warnings; V1 covers Keda's 58100.

SpellCast layout: ZoneServer 0x67a920. Recorded Boulder Storm warnings carry
unit XY direction and a final warning flag. S_Spell describes a straight-line
attack with a 30-tick windup. Unknown shapes are never guessed from their color.
"""
import asyncio
from dataclasses import dataclass
import math
import struct
import time
from wire import ProtocolError


@dataclass(frozen=True)
class Lane:
    caster: int
    origin: tuple
    direction: tuple
    expires: float
    spell: int = 58100
    length: float = 30.0
    half_width: float = 3.0  # Conservative clearance, not pixel-perfect geometry.

    def contains(self, point):
        dx, dy = point[0] - self.origin[0], point[1] - self.origin[1]
        ux, uy = self.direction
        return -1 <= dx * ux + dy * uy <= self.length + 1 and abs(dx * uy - dy * ux) <= self.half_width


def warning(payload, mobs, now):
    if len(payload) != 24:
        return None
    spell, caster, target, mode, x, y, z, marked = struct.unpack('<HIIBfffB', payload)
    mob = mobs.get(caster)
    if spell != 58100 or not marked or mob is None or mob.template != 41165:
        return None
    if not all(math.isfinite(v) for v in (x, y, z, *mob.position)):
        return None
    norm = math.hypot(x, y)
    if not .8 <= norm <= 1.2:
        return None
    return Lane(caster, tuple(mob.position), (x / norm, y / norm), now + 3.25)


def escape(lane, here, grid):
    if grid is None or not lane.contains(here):
        return None
    ux, uy = lane.direction
    candidates = [(here[0] + sign * -uy * 6, here[1] + sign * ux * 6) for sign in (-1, 1)]
    candidates.append((lane.origin[0] - ux * 4, lane.origin[1] - uy * 4))
    safe = []
    for point in candidates:
        try:
            point = grid.approach(point)
        except (ProtocolError, ValueError):
            continue
        if math.dist(here, point) <= 8 and not lane.contains(point) and grid.line_clear(here, point):
            safe.append(point)
    return min(safe, key=lambda point: math.dist(here, point)) if safe else None


class Controller:
    def __init__(self, context, emit=lambda *a, **k: None, clock=time.monotonic):
        self.context, self.emit, self.clock = context, emit, clock
        self.event = asyncio.Event()
        self.pending = None
        self.unknown = set()

    def clear(self):
        self.pending = None
        self.event.clear()

    def observe(self, name, payload):
        if name != 'SpellCast':
            return
        lane = warning(payload, self.context.combat.mobs, self.clock())
        if lane is None and len(payload) == 24:
            spell, caster, target, mode, x, y, z, marked = struct.unpack('<HIIBfffB', payload)
            if (marked and caster == self.context.combat.target and spell not in self.unknown
                    and len(self.unknown) < 20):
                self.unknown.add(spell)
                self.emit('warning', f'Dodge: warning spell {spell} has no verified shape profile yet.')
        here = self.context.position()
        if lane and here is not None and lane.contains(here):
            self.pending = lane
            self.event.set()

    async def avoid(self):
        lane = self.pending
        self.clear()
        if lane is None or lane.expires <= self.clock():
            return
        here = self.context.position()
        point = escape(lane, here, self.context.grid) if here is not None else None
        if point is None:
            self.emit('warning', 'Dodge: no clear escape for Boulder Storm; movement was not attempted.')
            return
        self.emit('info', f'Dodge: Boulder Storm warning; interrupting attacks and moving to {point[0]:.1f}, {point[1]:.1f}.')
        try:
            await asyncio.wait_for(self.context.walk(point), max(.1, lane.expires - self.clock() + .5))
        except (ProtocolError, asyncio.TimeoutError):
            self.emit('warning', 'Dodge: escape was not confirmed before the warning deadline.')
            return
        here = self.context.position()
        if here is None or lane.contains(here):
            self.emit('warning', 'Dodge: native position is still inside the warning lane.')
            return
        self.emit('info', 'Dodge: native movement confirmed outside the warning lane; waiting for the attack.')
        await asyncio.sleep(max(0, lane.expires - self.clock()))
