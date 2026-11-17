"""Per-kind objective drivers.

Each driver performs the ordinary player action the objective asks for and then
lets MissionServer decide: quest progress is only ever read back from
`ClientUpdateMissionState`. Drivers never report completion themselves, and a
quest is only finished when its live state becomes 4 (ready to turn in).

The context is a small bag of injected callables so these drivers stay free of
network setup and can be unit-tested with fakes:

    position()            current (x, y)
    walk(point)           collision-safe travel to a world point
    talk_to(template)     walk near a spawn and send TalkToNPC, returning its id
    send(name, payload)   raw zone send
    inventory             inventory.Inventory
"""
from dataclasses import dataclass
import asyncio
import math
import struct
import time
from wire import ProtocolError
from combat import collect, engage
from npc import READY, option_for_quest, parse_dialog


@dataclass
class Context:
    session: object
    combat: object
    scene: object
    inventory: object
    quest: object
    position: object
    walk: object
    talk_to: object
    send: object
    report: callable = print
    grid: object = None
    raw_send: object = None
    spell: int = None
    resources: object = frozenset((40334, 40335, 40336))
    prepare_combat: object = None


def nearest(point, points):
    if not points:
        return None
    return min(points, key=lambda other: math.dist(point, other))


async def approach(ctx, point, within=2.5, timeout=40):
    start = ctx.position()
    if start is None:
        raise ProtocolError('Cannot approach a target before the server sends a position')
    if math.dist(start, point) <= within:
        return
    if ctx.grid is not None:
        point = ctx.grid.approach(point)
    await ctx.walk(point)


async def wait_for(predicate, timeout=8, interval=.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(interval)
    return None


async def move_to_spawn(ctx, template, radius=45):
    points = ctx.scene.positions(template) if ctx.scene else []
    here = ctx.position()
    point = nearest(here, points) if points and here is not None else None
    if point is None:
        return False
    await approach(ctx, point, within=6)
    return True


async def follow_target(ctx, target):
    """Walk back into weapon reach of a victim that moved during the fight."""
    mob = ctx.combat.mobs.get(target)
    if mob is None or not mob.alive:
        return
    here = ctx.position()
    if here is None:
        return
    distance = math.dist(here, mob.position)
    if distance <= 1.2:
        return
    ctx.report(f'Following {target}: {distance:.2f} units behind at '
               f'({mob.position[0]:.2f},{mob.position[1]:.2f}).', flush=True)
    await approach(ctx, mob.position, within=1.2)


async def hunt(ctx, template, count):
    if template in ctx.resources:
        raise ProtocolError(f'Resource object {template} requires interaction, not combat')
    if ctx.prepare_combat is not None:
        await ctx.prepare_combat()
    killed = 0
    attempts = 0
    stalls = 0
    while killed < count:
        if ctx.quest is not None and ctx.session.states.get(ctx.quest.id) == READY:
            return killed
        attempts += 1
        if attempts > count * 6 + 6:
            raise ProtocolError(f'Could not find {template} to kill {count} time(s)')
        actor = ctx.combat.hunting(template, ctx.position(), radius=45)
        if actor is None:
            if not await move_to_spawn(ctx, template):
                raise ProtocolError(f'No authored spawn for {template}')
            actor = await wait_for(lambda: ctx.combat.hunting(template, ctx.position(), radius=45),
                                   timeout=10)
            if actor is None:
                continue
        mob = ctx.combat.mobs[actor]
        before = ctx.combat.kills
        try:
            # Melee only lands inside the weapon's own reach, and a hop can stop
            # a little short of its endpoint, so close to well inside it.
            await approach(ctx, mob.position, within=1.2)
            await engage(ctx.combat, ctx.raw_send or ctx.send, actor, timeout=180 if ctx.quest else 60,
                         report=ctx.report, spell=ctx.spell,
                         follow=lambda target: follow_target(ctx, target))
        except ProtocolError as error:
            stalls += 1
            ctx.report(f'Combat on {actor} stalled: {error}', flush=True)
            if stalls >= 3:
                raise
            continue
        # Mission progress comes from the monster's death, not from who struck
        # the last blow (the authored ally group fights these commanders too),
        # so any watched actor that is no longer alive counts here.
        current = ctx.combat.mobs.get(actor)
        if ctx.combat.kills > before or current is None or not current.alive:
            killed += 1
            stalls = 0
    return killed


async def loot(ctx, radius=6.0):
    position = ctx.position()
    if position is None:
        return []
    return await collect(ctx.combat, ctx.raw_send or ctx.send, position, radius=radius,
                         timeout=4, report=ctx.report)


async def drive_kill(ctx, objective):
    args = objective.args
    template = args[0]
    if template == 40338:
        return await wake_workers(ctx, objective)
    count = args[1] if len(args) > 1 else 1
    await hunt(ctx, template, count)


async def wake_workers(ctx, objective):
    """Quest 1010 uses the earned hammer; workers are never melee targets."""
    if ctx.quest.id != 1010:
        raise ProtocolError('Sleeping-worker interaction is verified only for quest 1010')
    location = ctx.inventory.require(30297)
    visited = set()
    def progress():
        return (ctx.session.states.get(ctx.quest.id), tuple(ctx.session.progress.get(ctx.quest.id, ())),
                tuple(sorted((key, value) for key, value in getattr(ctx.session, 'personal', {}).items()
                             if key >> 32 == ctx.quest.id)))
    for _ in range(6):
        if ctx.session.states.get(ctx.quest.id) == READY:
            return
        def target():
            actors = [mob for mob in ctx.combat.mobs.values() if mob.alive
                      and mob.template == 40338 and mob.id not in visited]
            return min(actors, key=lambda mob: math.dist(ctx.position(), mob.position)) if actors else None
        worker = target()
        if worker is None:
            if not await move_to_spawn(ctx, 40338):
                raise ProtocolError('Sleeping worker spawn unavailable')
            worker = await wait_for(target, timeout=10)
        if worker is None:
            raise ProtocolError('No unvisited sleeping worker in view')
        await approach(ctx, worker.position, within=1.2)
        await ctx.send('LeaveShop')
        await ctx.send('TalkToNPC', struct.pack('<I', 0))
        await ctx.send('TargetUpdate', struct.pack('<I', worker.id))
        before = progress()
        bag, slot = location
        # Native ItemUse Deserialize: container, bag, slot (i16), target and
        # expected item (i32), string, then three optional control i16 values.
        payload = struct.pack('<hhhIIHhhh', 0, bag, slot, worker.id, 30297, 0, 0, 0, 0)
        await ctx.send('ItemUse', payload)
        ctx.report(f'Quest 1010: using earned hammer 30297 on worker {worker.id}.', flush=True)
        if not await wait_for(lambda: progress() != before, timeout=12):
            raise ProtocolError('Hammer use did not produce confirmed quest progress')
        visited.add(worker.id)
        await asyncio.sleep(2)
    raise ProtocolError('Worker objective remains incomplete after bounded hammer attempts')


async def drive_collect_drop(ctx, objective):
    args = objective.args
    template = args[0]
    count = args[3] if len(args) > 3 else 1
    item = args[2] if len(args) > 2 else 0
    key = (ctx.quest.id << 32) | (2 << 16) | template
    def complete():
        return (ctx.session.states.get(ctx.quest.id) == READY or
                (item > 0 and ctx.inventory.stack_count(item) >= count) or
                getattr(ctx.session, 'personal', {}).get(key, 0) >= count)
    async def refresh():
        if item > 0:
            await ctx.inventory.refresh(ctx.send)
            ctx.report(f'Quest {ctx.quest.id}: item {item} '
                       f'{ctx.inventory.stack_count(item)}/{count} in native inventory.', flush=True)
    await refresh()
    if complete():
        return
    # Collection objectives may track owned stacks rather than a personal kill
    # counter. Refresh native inventory; attempts and cast ACKs are not progress.
    # READY belongs to the whole quest, not its first collection objective.
    if template in ctx.resources:
        # Scene kind 7 is the short resource harvest; kind 5 is the longer
        # use-object interaction (the raised mounds). They share biology class 5.
        kinds = {spawn.get('interaction') for spawn in getattr(ctx.scene, 'spawns', {}).values()
                 if spawn['template'] == template}
        skill = 62034 if kinds == {5} else 62033
        unavailable = set()
        def resource_actor():
            choices = [mob for mob in ctx.combat.mobs.values() if mob.alive and mob.template == template
                       and mob.id not in unavailable and math.dist(mob.position, ctx.position()) <= 60]
            return min(choices, key=lambda mob: math.dist(mob.position, ctx.position())) if choices else None
        for _ in range(count * 3):
            if complete():
                return
            actor = resource_actor()
            if actor is None:
                await move_to_spawn(ctx, template)
                actor = await wait_for(resource_actor, timeout=8)
            if actor is None:
                raise ProtocolError(f'Quest {ctx.quest.id}: no gatherable resource {template} visible')
            actor = actor.id
            await approach(ctx, ctx.combat.mobs[actor].position, within=1.2)
            await ctx.send('TargetUpdate', struct.pack('<I', actor))
            if hasattr(ctx.session, 'buffers'):
                ctx.session.buffers['SpellCastOK'] = []
            await ctx.send('SpellCastToLife', struct.pack('<HIH', skill, actor, 0))
            ctx.report(f'Quest {ctx.quest.id}: gathering resource {template} through native skill {skill}.', flush=True)
            ack = await ctx.session.expect('SpellCastOK',
                lambda raw: len(raw) == 12 and struct.unpack_from('<H', raw)[0] == skill
                and (struct.unpack_from('<i', raw, 6)[0] & 0xffffffff) == actor, timeout=5)
            _, ticks, _, accepted, _ = struct.unpack('<HiiBB', ack)
            if not accepted:
                unavailable.add(actor)
                ctx.report(f'Quest {ctx.quest.id}: resource {actor} unavailable; trying another object.', flush=True)
                await asyncio.sleep(1)
                continue
            await asyncio.sleep(max(.5, min(12, ticks / 10 + .5)))
            await loot(ctx, radius=6)
            await asyncio.sleep(.5)
            await refresh()
        if not complete():
            raise ProtocolError(f'Quest {ctx.quest.id}: gathering did not complete objective {template}')
        return
    for _ in range(count * 2 + 2):
        if complete():
            return
        await hunt(ctx, template, 1)
        await loot(ctx)
        await refresh()
    await loot(ctx)
    await refresh()
    if not complete():
        raise ProtocolError(f'Quest {ctx.quest.id}: drop objective {template} made insufficient progress')


async def drive_talk(ctx, objective):
    template = objective.args[0] if objective.args else ctx.quest.return_npc
    if not template:
        raise ProtocolError(f'Quest {ctx.quest.id}: no NPC for a bare NPCTalk')
    actor = await ctx.talk_to(template)
    if not actor:
        return
    # The native client selects the quest's dialog entry; that interaction is what
    # the server counts. A plain NPC without an entry still gets the bare talk.
    view = await ctx.session.talk(actor)
    position = option_for_quest(view, ctx.quest.id)
    if position is not None:
        await ctx.session.choose(view, position)


async def drive_travel(ctx, objective):
    if not objective.args:
        raise ProtocolError(f'Quest {ctx.quest.id}: AreaTravel without an area id')
    area = ctx.scene.area(objective.args[0]) if ctx.scene else None
    if area is None:
        raise ProtocolError(f'Quest {ctx.quest.id}: unknown travel area {objective.args[0]}')
    x, y, _ = area
    await approach(ctx, (x, y), within=1.0)


async def drive_collect(ctx, objective):
    args = objective.args
    if len(args) >= 5:
        await approach(ctx, (args[3], args[4]), within=1.5)
    await loot(ctx, radius=6.0)
    if ctx.session.states.get(ctx.quest.id) != READY and len(args) >= 2:
        # Fall back to ordinary kills near the collection point.
        template = None
        point = ctx.position()
        if point is not None:
            near = [mob for mob in ctx.combat.mobs.values()
                    if mob.alive and math.dist(mob.position, point) <= 25]
            if near:
                template = min(near, key=lambda mob: math.dist(mob.position, point)).template
        if template is not None:
            await hunt(ctx, template, 1)
            await loot(ctx)


async def drive_equip(ctx, objective):
    item = objective.args[0]
    location = ctx.inventory.first(item)
    if location is None:
        # The accept actions grant the item in the same breath as the ACTIVE
        # state, so give the inventory packet a moment to arrive.
        location = await wait_for(lambda: ctx.inventory.first(item), timeout=5)
    if location is None:
        # Already equipped, or granted in a form we cannot place; the state is the judge.
        return
    await ctx.send('LeaveShop')
    await asyncio.sleep(.5)
    await ctx.send('SwitchItemLocation', ctx.inventory.equip_payload(*location))
    result = await ctx.session.expect('SwitchItemLocationOK', timeout=8)
    if not result or result[-1] != 1:
        raise ProtocolError(f'Quest {ctx.quest.id}: equipping item {item} was rejected')
    ctx.inventory.discard(*location)


async def drive_buff(ctx, objective):
    # Accept actions either apply a timed buff or grant a usable item. Nothing can be
    # asserted until the server pushes the next state, so this driver only waits.
    await ctx.session.state(ctx.quest.id, (3, READY), timeout=5)


async def drink_quest_potion(ctx, objective):
    """Activate the medicine granted by quest 1014, then require native READY."""
    if ctx.quest.id != 1014:
        raise ProtocolError('Quest potion semantics are verified only for quest 1014')
    bag, slot = ctx.inventory.require(30300)
    await ctx.send('LeaveShop')
    await ctx.send('TalkToNPC', struct.pack('<I', 0))
    payload = struct.pack('<hhhIIHhhh', 0, bag, slot, ctx.combat.player_id, 30300, 0, 0, 0, 0)
    await ctx.send('ItemUse', payload)
    ctx.report('Quest 1014: drinking the owned refreshing potion 30300.', flush=True)
    await ctx.session.state(ctx.quest.id, READY, timeout=15)


async def drive_deliver(ctx, objective):
    template = objective.args[0] if objective.args else ctx.quest.return_npc
    key = (ctx.quest.id << 32) | (4 << 16) | template
    count = objective.args[3] if len(objective.args) > 3 else 1
    if getattr(ctx.session, 'personal', {}).get(key, 0) >= count:
        return
    if not template or (ctx.scene and not ctx.scene.positions(template)):
        raise ProtocolError(f'Quest {ctx.quest.id}: delivery NPC {template} is not on this map')
    actor = await ctx.talk_to(template)
    view = await ctx.session.talk(actor)
    dialog_id = objective.args[1] if len(objective.args) > 1 else None
    if view.ident == dialog_id:
        return
    choices = [i for i, option in enumerate(view.options)
               if option.index == dialog_id or str(dialog_id) in option.text.split()]
    if not choices:
        position = option_for_quest(view, ctx.quest.id)
        if position is not None:
            choices = [position]
    if len(choices) != 1:
        raise ProtocolError(f'Quest {ctx.quest.id}: delivery dialog {dialog_id} not identified; '
                            f'NPC {template} offered {[(o.index,o.text) for o in view.options]}')
    await ctx.session.choose(view, choices[0])
    await ctx.session.expect('DisplayDialogView',
        lambda raw: parse_dialog(raw).ident == dialog_id, timeout=8)
    confirmed = await wait_for(lambda: ctx.session.personal.get(key, 0) >= count
                              or ctx.session.states.get(ctx.quest.id) == READY, timeout=8)
    if not confirmed:
        raise ProtocolError(f'Quest {ctx.quest.id}: server did not confirm delivery to {template}')


async def drive_use_item(ctx, objective):
    if objective.command != 'NPCItem':
        raise ProtocolError(f'Quest {ctx.quest.id}: {objective.command} requires a verified item-use action')
    template = ctx.quest.return_npc or ctx.quest.accept_npc
    if not template or (ctx.scene and not ctx.scene.positions(template)):
        raise ProtocolError(f'Quest {ctx.quest.id}: item target is not on this map')
    actor = await ctx.talk_to(template)
    view = await ctx.session.talk(actor)
    position = option_for_quest(view, ctx.quest.id)
    if position is not None:
        await ctx.session.choose(view, position)


async def drive_wait(ctx, objective):
    await ctx.session.state(ctx.quest.id, (3, READY), timeout=5)


DRIVERS = {
    'kill': drive_kill,
    'collect_drop': drive_collect_drop,
    'talk': drive_talk,
    'travel': drive_travel,
    'collect': drive_collect,
    'equip': drive_equip,
    'buff': drive_buff,
    'deliver': drive_deliver,
    'use_item': drive_use_item,
    'level': drive_wait,
}


def driver_for(kind):
    return DRIVERS.get(kind)


async def run(quest, ctx, timeout=300, plan=None):
    """Drive every authored objective, then wait for the server to mark it ready."""
    from quests import objective_plan
    objectives = plan if plan is not None else objective_plan(quest)
    for objective in objectives:
        if ctx.session.states.get(quest.id) == READY:
            return
        driver = driver_for(objective.kind)
        if driver is None:
            raise ProtocolError(f'Quest {quest.id}: no driver for {objective.command}')
        ctx.report(f'Quest {quest.id}: objective {objective.index + 1}/'
                   f'{len(objectives)} {objective.command}.', flush=True)
        await driver(ctx, objective)
    await ctx.session.state(quest.id, READY, timeout)
