"""Native battle capability snapshots, acknowledged skills and owned gear upgrades."""
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import time
from item_stream import equipment, inventory
from wire import ProtocolError, Reader


@dataclass(frozen=True)
class Skill:
    id: int
    name: str
    cooldown: float


# Conservative spacing exceeds these starter skills' ordinary cooldowns.
# No dash, area, toggle, hold-to-cast or unverified healing action is automated.
SKILLS = (Skill(51402, 'Shield Bash', 12), Skill(51401, 'Sword Slash', 6))


def learned_skills(payload):
    gear, data = equipment(payload)
    count = data.number('h')
    if not 0 <= count <= 512:
        raise ProtocolError('Invalid learned-skill count')
    skills = {data.number('H'): data.number('B') for _ in range(count)}
    slots = data.number('h')
    if not 0 <= slots <= 32:
        raise ProtocolError('Invalid spell-slot count')
    for _ in range(slots): data.number('H')
    data.end()
    return gear, skills


def player_stats(payload):
    data = Reader(payload)
    ident = data.number('I')
    for _ in range(4): data.text()
    speed = data.number('f')
    data.number('B')
    data.take(4)
    level, hp, secondary = data.number('H'), data.number('i'), data.number('i')
    # The second integer was previously mislabeled max HP. Its semantics are
    # not established, so it must not drive percentage-based healing decisions.
    if not 1 <= level <= 1000 or hp < 0 or not 0 < speed < 1000:
        raise ProtocolError('Invalid native player-stat prefix')
    return dict(actor=ident, level=level, hp=hp, maximum_hp=None, movement=speed)


def upgrade_candidates(bag, worn, catalog, level):
    """Strict base-stat upgrades from owned, level-eligible ordinary gear only."""
    current = {}
    for (page, slot), item in worn.items():
        if page != 0: continue
        definition = catalog.get(str(item.id))
        if definition:
            current[definition['type']] = max(current.get(definition['type'], 0), definition['score'])
    candidates = []
    for location, item in bag.items():
        definition = catalog.get(str(item.id))
        if (definition and 1 <= definition['level'] <= level
                and definition['score'] > current.get(definition['type'], 0)):
            candidates.append((definition['score'] - current.get(definition['type'], 0), location, item.id))
    return sorted(candidates, key=lambda value: (-value[0], value[1]))


class Controller:
    def __init__(self, emit=lambda level, message: None, clock=time.monotonic, catalog=None):
        self.emit, self.clock = emit, clock
        self.catalog = catalog or {}
        self.stats = None
        self.stats_at = float('-inf')
        self.learned, self.worn, self.bag = {}, {}, {}
        self.next_cast = {}
        self.disabled = set()
        self.cast_failures = {}
        self.peak_hp = 0
        self.next_potion = 0
        self.pending_cast = None
        self.pending_swap = None
        self.global_ready = 0
        self.revisions = dict(stats=0, gear=0, bag=0)
        self.swap_rejected = set()

    def observe(self, name, payload):
        if name == 'EnterNodePlayerData':
            self.stats = player_stats(payload)
            self.peak_hp = max(self.peak_hp, self.stats['hp'])
            self.stats_at = self.clock()
            self.revisions['stats'] += 1
        elif name == 'EnterNodeEquipAndSpell':
            self.worn, self.learned = learned_skills(payload)
            self.revisions['gear'] += 1
        elif name == 'EnterNodeInventory':
            self.bag, _ = inventory(payload)
            self.revisions['bag'] += 1
        elif name == 'SpellCastOK':
            if len(payload) == 12:
                spell, duration, target, accepted, _ = struct.unpack('<HiiBB', payload)
                # Native values 19/35 correspond to 1.9/3.5-second casts in
                # observed Gather/potion flows. Do not cancel them with melee.
                delay = max(.5, min(10, duration / 10))
            else:
                return
            if self.pending_cast and self.pending_cast[0:2] == (spell, target & 0xffffffff):
                future = self.pending_cast[2]
                if not future.done(): future.set_result((bool(accepted), delay))
        elif name == 'SwitchItemLocationOK' and len(payload) == 13 and self.pending_swap:
            values = struct.unpack('<hhhhhhB', payload)
            bag, slot, future = self.pending_swap
            if values[:3] == (0, slot, bag) and not future.done():
                future.set_result(values[-1] == 1)
        elif name == 'CommandFailReturn' and len(payload) == 8:
            command, reason = struct.unpack('<ii', payload)
            if command == 74 and self.pending_cast and reason == self.pending_cast[0]:
                future = self.pending_cast[2]
                if not future.done(): future.set_result((False, .5))

    async def refresh(self, send, fields=('stats',)):
        before = dict(self.revisions)
        names = dict(stats='EnterNodePlayerData', gear='EnterNodeEquipAndSpell', bag='EnterNodeInventory')
        for field in fields: await send(names[field], b'')
        deadline = self.clock() + 8
        while self.clock() < deadline:
            if all(self.revisions[field] > before[field] for field in fields): return
            await asyncio.sleep(.05)
        raise ProtocolError('Battle capability refresh timed out')

    async def prepare(self, send):
        await self.refresh(send, ('stats', 'gear', 'bag'))
        # Absolute HP floor only; do not pretend the unverified prefix field is
        # maximum HP. Rest outside combat and refresh before choosing a fight.
        for _ in range(6):
            if self.stats['hp'] >= 100: break
            self.emit('info', 'Battle: resting before combat because current HP is below 100.')
            await asyncio.sleep(5)
            await self.refresh(send)
        if self.stats['hp'] < 100:
            raise ProtocolError('Battle deferred: HP remains below the conservative minimum')
        options = [row for row in upgrade_candidates(self.bag, self.worn, self.catalog, self.stats['level'])
                   if row[2] not in self.swap_rejected]
        if options:
            _, (bag, slot), ident = options[0]
            future = asyncio.get_running_loop().create_future()
            self.pending_swap = (bag, slot, future)
            try:
                await send('LeaveShop', b'')
                await send('TalkToNPC', struct.pack('<I', 0))
                await send('SwitchItemLocation', struct.pack('<hhhhhh', 0, slot, bag, 1, -1, 0))
                if not await asyncio.wait_for(future, 8):
                    self.swap_rejected.add(ident)
                    self.emit('warning', f'Gear: native equip rejected item {ident}; keeping current gear.')
                else:
                    await self.refresh(send, ('gear', 'bag'))
                    if not any(page == 0 and item.id == ident for (page, _), item in self.worn.items()):
                        raise ProtocolError('Gear swap acknowledgement did not match refreshed equipment')
                    self.emit('info', f'Gear: equipped owned base-stat upgrade {ident}; native equipment confirmed.')
            finally:
                self.pending_swap = None

    async def action(self, send, target):
        # The owned starter potion restores 50 HP/s for 10s (enchant 35001).
        # Refresh actual HP rather than inferring it from animation packets.
        if self.stats is not None and self.clock() - self.stats_at >= 3:
            await self.refresh(send)
        if self.stats is not None and self.stats['hp'] < max(300, self.peak_hp * .65):
            await self.use_owned_potion(send)
        now = self.clock()
        if self.pending_cast or now < self.global_ready: return False
        choices = [s for s in SKILLS if self.learned.get(s.id, 0) > 0 and s.id not in self.disabled
                   and now >= self.next_cast.get(s.id, 0)]
        if not choices: return False
        skill = choices[0]
        future = asyncio.get_running_loop().create_future()
        self.pending_cast = (skill.id, target, future)
        self.next_cast[skill.id] = now + skill.cooldown
        try:
            await send('SpellCastToLife', struct.pack('<HIH', skill.id, target, 0))
            try:
                accepted, delay = await asyncio.wait_for(future, 2)
            except asyncio.TimeoutError:
                accepted, delay = False, .5
            self.global_ready = self.clock() + delay
            if accepted:
                self.cast_failures.pop(skill.id, None)
                self.emit('info', f'Battle: {skill.name} accepted by the native server.')
                await asyncio.sleep(delay)
                return True
            failures = self.cast_failures.get(skill.id, 0) + 1
            self.cast_failures[skill.id] = failures
            backoff = min(120, skill.cooldown * 2 ** min(failures, 3))
            self.next_cast[skill.id] = self.clock() + backoff
            self.emit('warning', f'Battle: {skill.name} was rejected or unconfirmed; '
                      f'retry after {backoff:.0f}s, using melee meanwhile.')
            return False
        finally:
            self.pending_cast = None

    async def use_owned_potion(self, send):
        if self.clock() < self.next_potion:
            return
        await self.refresh(send, ('bag',))
        held = next(((location, item) for location, item in sorted(self.bag.items())
                     if item.id == 10534 and item.durability > 0), None)
        if held is None:
            self.next_potion = self.clock() + 30
            return
        (bag, slot), item = held
        before = sum(max(0, i.durability) for i in self.bag.values() if i.id == 10534)
        self.next_potion = self.clock() + 15
        await send('ItemUse', struct.pack('<hhhIIHhhh', 0, bag, slot,
                                         self.stats['actor'], 10534, 0, 0, 0, 0))
        await asyncio.sleep(.5)
        await self.refresh(send, ('bag',))
        after = sum(max(0, i.durability) for i in self.bag.values() if i.id == 10534)
        if after < before:
            self.emit('info', 'Battle: native inventory confirmed use of an owned Tiny HP Potion.')
        else:
            self.next_potion = self.clock() + 30
            self.emit('warning', 'Battle: potion consumption unconfirmed; backing off 30s.')

    def summary(self):
        return dict(stats=self.stats, learned_skills={str(s.id): self.learned.get(s.id, 0) for s in SKILLS},
                    disabled_skills=sorted(self.disabled), equipment={str(slot): item.id
                        for (page, slot), item in self.worn.items() if page == 0},
                    owned_upgrade_candidates=len(upgrade_candidates(self.bag, self.worn, self.catalog,
                        self.stats['level'] if self.stats else 0)))
