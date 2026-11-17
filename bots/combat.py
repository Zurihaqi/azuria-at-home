"""Target selection, melee pacing and loot bookkeeping.

The server owns combat timing. CNE_CZ_ZoneServerTargetUpdate pins ch+0xc14, and
CNE_CZ_ZoneServerMeleeAttack is only accepted when its target equals that victim,
lives in the same node and is still alive; damage is then scheduled by
CEventDelayDamageCut at the weapon's motion end and gated by
CCharacter::UpdateAttackDownTime. So the bot never fakes an animation: it selects,
strikes at a cadence the server tolerates, and watches for CNC_CZ_ClientDie.

Nothing here guesses at quest progress. A kill only counts once MissionServer
observes the death and pushes CNC_CZ_ClientUpdateMissionState, so the objective
driver keys off that packet, not off this module.
"""
from dataclasses import dataclass
import asyncio
import math
import struct
import time
from wire import ProtocolError, Reader


# Client packets this module consumes, resolved through the caller's protocol map.
SEEN = ('CNC_CZ_ClientSeeMob', 'CNC_CZ_ClientMeleeAttack', 'CNC_CZ_ClientDie',
        'CNC_CZ_ClientSeeTreasure', 'CNC_CZ_ClientTreasurePickupOK',
        'CNC_CZ_ClientMoveChar', 'CNC_CZ_ClientTreasureDisappear')


@dataclass
class Mob:
    id: int
    template: int
    name: str
    position: tuple
    alive: bool = True


class Cadence:
    """Adaptive melee interval, converging down onto the server's own downtime."""

    MINIMUM = .4
    MAXIMUM = 6.0

    def __init__(self, interval=1.5):
        self.interval = interval
        self.successes = 0

    def accepted(self):
        self.successes += 1
        if self.successes >= 4:
            self.successes = 0
            self.interval = max(self.interval * .95, self.MINIMUM)

    def rejected(self):
        # The attack was cancelled, so the next one must wait out the downtime.
        self.successes = 0
        self.interval = min(self.interval * 1.5, self.MAXIMUM)

    def cooldown(self):
        return self.interval + .05


class Combat:
    def __init__(self, protocol, player_id):
        self.protocol = protocol
        self.player_id = player_id
        self.mobs = {}
        self.treasures = {}
        self.target = None
        self.cadence = Cadence()
        self.acks = 0
        self.pickups = 0
        self.kills = 0
        self.pickup_acks = []
        self.self_reports = 0
        self.learning = None  # Optional observer; never required for gameplay.
        self.controller = None
        self.evasion = None
        # Stamped by the host when CLIENT_DIE names this character:
        # (killer biology template or id, monotonic seconds). The quest engine
        # uses it to charge a native death to the retry budget.
        self.last_death = None
        missing = [name for name in SEEN if name not in protocol]
        if missing:
            raise ProtocolError('Protocol map is missing ' + ', '.join(missing))
        self.see_mob = protocol['CNC_CZ_ClientSeeMob']
        self.melee_attack = protocol['CNC_CZ_ClientMeleeAttack']
        self.die = protocol['CNC_CZ_ClientDie']
        self.see_treasure = protocol['CNC_CZ_ClientSeeTreasure']
        self.pickup_ok = protocol['CNC_CZ_ClientTreasurePickupOK']
        self.move_char = protocol['CNC_CZ_ClientMoveChar']
        self.treasure_gone = protocol['CNC_CZ_ClientTreasureDisappear']

    # ---- outbound ------------------------------------------------------
    def target_payload(self, target_id):
        return struct.pack('<I', target_id)

    def attack_payload(self, target_id, mode=0):
        return struct.pack('<IB', target_id, mode)

    def pickup_payload(self, treasure_id):
        return struct.pack('<I', treasure_id)

    # ---- inbound -------------------------------------------------------
    def reset(self):
        """Drop actor and loot state; called whenever the character enters a node."""
        self.mobs.clear()
        self.treasures.clear()
        self.target = None

        if self.evasion is not None:
            self.evasion.clear()

    def observe(self, opcode, payload):
        """Update world state from one client packet; returns log-worthy events."""
        if self.learning is not None:
            self.learning.observe(opcode, payload)
        if opcode == self.protocol.get('CNC_CZ_ClientCantSee') and len(payload) == 4:
            self.mobs.pop(struct.unpack('<I', payload)[0], None)
            return []
        if opcode == self.protocol.get('CNC_CZ_ClientMovePrediction') and len(payload) in (32, 36):
            # Native constructor rounds world coordinates * 16 into uint16.
            # These are authoritative segment-start positions, not the optional
            # future destination. Using SeeMob alone leaves roaming targets stale.
            actor, x, y = struct.unpack_from('<IHH', payload)
            mob = self.mobs.get(actor)
            if mob is not None:
                mob.position = (x / 16.0, y / 16.0)
            return []
        if opcode == self.see_mob:
            return self._see_mob(payload)
        if opcode == self.melee_attack and len(payload) in (16, 18):
            # ZoneServer serializes Attacker, Victim, Damage, Result, ActionID
            # and (current builds) HurtActionID; older captures stop after
            # Result/ActionID. All six fields are meaningful for damage logs.
            if len(payload) == 18:
                attacker, victim, damage, _, _, _ = struct.unpack('<IIihhh', payload)
            else:
                attacker, victim, damage, _, _ = struct.unpack('<IIihh', payload)
            if attacker == self.player_id:
                self.acks += 1
                return [f'Melee landed on {victim} for {damage}.']
            return [f'Melee: {attacker} hit {victim} for {damage}.']
        if opcode == self.die and len(payload) == 11:
            victim, killer, flags, revive = struct.unpack('<IIBH', payload)
            mob = self.mobs.get(victim)
            if mob is not None:
                mob.alive = False
            if victim == self.player_id:
                self.target = None
                return [f'Pilot died; killer={killer}, flags={flags}, revive={revive}.']
            if killer == self.player_id and mob is not None:
                self.kills += 1
                return [f'Killed {mob.name or mob.template} ({victim}).']
            return []
        if opcode == self.see_treasure and len(payload) >= 12:
            ident, x, y = struct.unpack_from('<Iff', payload)
            self.treasures[ident] = (x, y)
            return [f'Treasure {ident} dropped at ({x:.2f},{y:.2f}).']
        if opcode == self.pickup_ok and len(payload) >= 4:
            ident, = struct.unpack_from('<I', payload)
            self.pickup_acks.append(ident)
            self.pickups += 1
            self.treasures.pop(ident, None)
            return [f'Treasure {ident} collected.']
        if opcode == self.treasure_gone and len(payload) >= 4:
            ident, = struct.unpack_from('<I', payload)
            self.treasures.pop(ident, None)
            return []
        if opcode == self.move_char and len(payload) == 12:
            who, x, y = struct.unpack('<iff', payload)
            if who == self.player_id:
                self.self_reports += 1
                return []
            mob = self.mobs.get(who)
            if mob is not None and math.isfinite(x) and math.isfinite(y):
                mob.position = (x, y)
            return []
        return []

    def _see_mob(self, payload):
        try:
            data = Reader(payload)
            mob_id, template, _ = data.number('I'), data.number('H'), data.number('b')
            x, y, _, _, _ = (data.number('f') for _ in range(5))
            data.number('b')
            data.number('I')
            name = data.text()
        except ProtocolError:
            return []
        if not (math.isfinite(x) and math.isfinite(y)):
            return []
        self.mobs[mob_id] = Mob(mob_id, template, name, (x, y))
        return [f'Saw {name or template} ({mob_id}) at ({x:.2f},{y:.2f}).']

    # ---- queries -------------------------------------------------------
    def alive(self, mob_id):
        mob = self.mobs.get(mob_id)
        return mob is not None and mob.alive

    def nearest(self, template, position, radius=30.0):
        if position is None:
            return None
        candidates = [mob for mob in self.mobs.values()
                      if mob.alive and mob.template == template
                      and math.dist(mob.position, position) <= radius]
        if not candidates:
            return None
        return min(candidates, key=lambda mob: math.dist(mob.position, position))

    def hunting(self, template, position, radius=30.0):
        """The nearest live mob of a template, re-resolved as earlier ones die."""
        mob = self.nearest(template, position, radius)
        return None if mob is None else mob.id


async def _await_count(combat, attribute, before, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if getattr(combat, attribute) > before:
            return True
        await asyncio.sleep(.02)
    return False


async def engage(combat, send, target_id, timeout=60.0, report=print, spell=None,
                 spell_interval=3.0, follow=None, record=True):
    """Keep encounter observation alive independently of cancelled activities."""
    learning = getattr(combat, 'learning', None) if record else None
    mob = combat.mobs.get(target_id)
    if learning is not None and mob is not None and mob.alive:
        learning.begin(combat.player_id, target_id, mob.template)
    try:
        return await _engage_avoiding(combat, send, target_id, timeout, report, spell,
                                      spell_interval, follow)
    except ProtocolError as error:
        if learning is not None:
            learning.finish('timeout' if 'did not die within' in str(error) else 'interrupted')
        raise
    finally:
        if learning is not None:
            learning.finish('interrupted')


async def _engage_avoiding(combat, send, target_id, timeout, report, spell, spell_interval, follow):
    evasion = getattr(combat, 'evasion', None)
    if evasion is None:
        return await _engage(combat, send, target_id, timeout, report, spell, spell_interval, follow)
    deadline = time.monotonic() + timeout
    fight = threat = None
    try:
        while combat.alive(target_id) and time.monotonic() < deadline:
            if evasion.event.is_set():
                await evasion.avoid()
                if follow is not None and combat.alive(target_id):
                    await follow(target_id)
                continue
            fight = asyncio.create_task(_engage(combat, send, target_id,
                max(.1, deadline - time.monotonic()), report, spell, spell_interval, follow))
            threat = asyncio.create_task(evasion.event.wait())
            done, _ = await asyncio.wait((fight, threat), return_when=asyncio.FIRST_COMPLETED)
            if fight in done:
                return await fight
            # Stop and await attacks/pursuit before giving movement to dodging.
            fight.cancel()
            await asyncio.gather(fight, return_exceptions=True)
            fight = None
            threat = None
        if combat.alive(target_id):
            raise ProtocolError(f'Combat target {target_id} did not die within {timeout:.0f}s')
        return True
    finally:
        pending = [task for task in (fight, threat) if task is not None]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


async def _engage(combat, send, target_id, timeout=60.0, report=print, spell=None,
                 spell_interval=3.0, follow=None):
    """Target one actor and melee it until ClientDie or the deadline.

    When the character's weapon grants a spell, the native client presses that
    shortcut between melee swings; the same two actions are replayed here.

    A rejected swing usually means the victim walked out of the weapon's reach
    (or the server dropped the pinned victim), so after two unacknowledged
    swings the caller's `follow(target_id)` walks the character back in and the
    victim is re-selected, exactly as a client player would.
    """
    mob = combat.mobs.get(target_id)
    if mob is None:
        raise ProtocolError(f'Combat target {target_id} is not in view')
    if not mob.alive:
        return True
    if combat.target != target_id:
        # Cooldown/range failures against an earlier actor must not leave every
        # subsequent enemy at the six-second maximum attack interval.
        combat.cadence.interval = min(combat.cadence.interval, 1.5)
        combat.cadence.successes = 0
    await send(combat.protocol['CNE_CZ_ZoneServerTargetUpdate'], combat.target_payload(target_id))
    combat.target = target_id
    deadline = time.monotonic() + timeout
    next_spell = 0.0
    misses = 0
    while time.monotonic() < deadline:
        # SeeMob can arrive again for the same actor, replacing the tracked
        # object, so resolve the live record on every pass.
        mob = combat.mobs.get(target_id)
        if mob is None:
            raise ProtocolError(f'Combat target {target_id} left view before it died')
        if not mob.alive:
            return True
        if combat.controller is not None:
            await combat.controller.action(
                lambda name, body=b'': send(combat.protocol['CNE_CZ_ZoneServer' + name], body), target_id)
            if not combat.alive(target_id):
                return True
        if spell and time.monotonic() >= next_spell:
            await send(combat.protocol['CNE_CZ_ZoneServerSpellCastToLife'],
                       struct.pack('<HIH', spell, target_id, 0))
            report(f'Cast spell {spell} on {target_id}.', flush=True)
            next_spell = time.monotonic() + spell_interval
        before = combat.acks
        await send(combat.protocol['CNE_CZ_ZoneServerMeleeAttack'],
                   combat.attack_payload(target_id))
        if await _await_count(combat, 'acks', before, combat.cadence.cooldown() * 2 + .5):
            combat.cadence.accepted()
            misses = 0
        else:
            combat.cadence.rejected()
            misses += 1
            report(f'Melee on {target_id} was not acknowledged; cadence now '
                   f'{combat.cadence.interval:.2f}s.', flush=True)
            if misses >= 2:
                misses = 0
                if follow is not None:
                    await follow(target_id)
                    if not combat.alive(target_id):
                        return True
                await send(combat.protocol['CNE_CZ_ZoneServerTargetUpdate'],
                           combat.target_payload(target_id))
                combat.target = target_id
        await asyncio.sleep(combat.cadence.cooldown())
    raise ProtocolError(f'Combat target {target_id} did not die within {timeout:.0f}s')


async def collect(combat, send, position, radius=4.0, timeout=4.0, report=print):
    """Pick up confirmed-droppable treasure within radius of the character."""
    picked = []
    for ident, spot in sorted(combat.treasures.items()):
        if math.dist(position, spot) > radius:
            continue
        before = combat.pickups
        await send(combat.protocol['CNE_CZ_ZoneServerTreasurePickup'],
                   combat.pickup_payload(ident))
        if await _await_count(combat, 'pickups', before, timeout):
            picked.append(ident)
        else:
            report(f'Treasure {ident} was not confirmed; leaving it for a later pass.', flush=True)
    return picked
