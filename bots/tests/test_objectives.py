from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content import Objective
import objectives
from npc import READY
from wire import ProtocolError
from combat import Mob


def objective(kind, args, command='Test'):
    return Objective(kind, args, command)


class FakeSession:
    def __init__(self, dialog=()):
        self.states = {}
        self.progress = {}
        self.talked = []
        self.chosen = []
        self.waits = []
        self.sent = []
        self.accept_ok = True
        self.dialog = dialog

    async def talk(self, actor):
        self.talked.append(actor)
        return SimpleNamespace(ident=actor, options=tuple(
            SimpleNamespace(index=index, text=text, kind=1)
            for index, text in enumerate(self.dialog)))

    async def choose(self, view, position):
        self.chosen.append(position)

    async def send(self, name, payload=b''):
        self.sent.append((name, payload))

    async def expect(self, name, timeout=15):
        return struct.pack('<hhhhhhB', 0, 0, 0, 0, 0, 0, int(self.accept_ok))

    async def state(self, quest, expected, timeout=15):
        self.waits.append((quest, expected))
        choices = expected if isinstance(expected, tuple) else (expected,)
        if self.states.get(quest) in choices:
            return self.states[quest]
        raise ProtocolError(f'Quest {quest}: expected {choices}, saw {self.states.get(quest)}')


class FakeInventory:
    def __init__(self, location):
        self.location = location
        self.discarded = []
        self.counts = {}

    def stack_count(self, item):
        return self.counts.get(item, 0)

    async def refresh(self, send):
        pass

    def first(self, item):
        return self.location

    def equip_payload(self, bag, slot, page=0):
        return struct.pack('<hhhhhh', 0, slot, bag, 1, -1, page)

    def discard(self, bag, slot):
        self.discarded.append((bag, slot))


class FakeScene:
    def __init__(self, areas=None):
        self.areas = areas or {}

    def area(self, ident):
        return self.areas.get(ident)

    def positions(self, template):
        return []


def context(quest=None, session=None, inventory=None, position=(0.0, 0.0),
            scene=None, grid=None):
    session = session or FakeSession()
    return objectives.Context(
        session=session, combat=None, scene=scene or FakeScene(),
        inventory=inventory or FakeInventory(None),
        quest=quest or SimpleNamespace(id=1, return_npc=10205),
        position=lambda: position, walk=_recorder('walk'), talk_to=_talker(55),
        send=session.send, report=lambda *a, **k: None, grid=grid)


def _recorder(name):
    calls = []

    async def call(*args):
        calls.append(args)
    call.calls = calls
    call.__name__ = name
    return call


class HammerTests(unittest.IsolatedAsyncioTestCase):
    async def test_supply_crates_use_resource_catalog_and_gather_not_melee(self):
        ctx = context(quest=SimpleNamespace(id=1020))
        ctx.session.states[1020] = 3
        ctx.resources = frozenset({40337})
        ctx.combat = SimpleNamespace(mobs={44: Mob(44,40337,'Supplies',(0,0))})
        ctx.scene.spawns = {1:dict(template=40337,interaction=7),2:dict(template=40337,interaction=6)}
        async def ack(name, predicate, timeout):
            return struct.pack('<HiiBB',62033,20,44,1,0)
        ctx.session.expect = ack
        sent=[]
        async def send(name,payload=b''):
            sent.append(name)
            if name=='SpellCastToLife':
                self.assertEqual(struct.unpack('<HIH',payload),(62033,44,0))
                ctx.inventory.counts[30302]=ctx.inventory.stack_count(30302)+1
        ctx.send=send
        from unittest.mock import AsyncMock
        with patch('objectives.asyncio.sleep',new=AsyncMock()), patch('objectives.loot',new=AsyncMock()):
            await objectives.drive_collect_drop(ctx,objective('collect_drop',(40337,100,30302,3)))
        self.assertEqual(sent.count('SpellCastToLife'),3)
        self.assertNotIn('MeleeAttack',sent)

    async def test_resource_cannot_enter_generic_hunting_driver(self):
        ctx=context()
        ctx.resources=frozenset({40337})
        with self.assertRaisesRegex(ProtocolError,'requires interaction'):
            await objectives.hunt(ctx,40337,1)

    async def test_mound_objective_uses_gather_and_does_not_require_entire_quest_ready(self):
        ctx = context(quest=SimpleNamespace(id=1017), position=(0, 0))
        ctx.session.states[1017] = 3
        ctx.session.personal = {}
        actor = Mob(44, 40336, 'Mound', (0, 0))
        ctx.combat = SimpleNamespace(nearest=lambda *a, **k: actor, mobs={44: actor})
        ctx.scene.spawns = {1:dict(template=40336, interaction=5)}
        async def ack(name, predicate, timeout):
            return struct.pack('<HiiBB', 62034, 80, 44, 1, 0)
        ctx.session.expect = ack
        sent = []
        async def send(name, payload=b''):
            sent.append(name)
            if name == 'SpellCastToLife':
                self.assertEqual(struct.unpack('<HIH', payload), (62034, 44, 0))
                ctx.inventory.counts[30301] = ctx.inventory.stack_count(30301) + 1
        ctx.send = send
        from unittest.mock import AsyncMock
        with patch('objectives.asyncio.sleep', new=AsyncMock()), patch('objectives.loot', new=AsyncMock()):
            await objectives.drive_collect_drop(ctx, objective('collect_drop', (40336, 100, 30301, 4)))
        self.assertEqual(sent.count('SpellCastToLife'), 4)
        self.assertNotIn('MeleeAttack', sent)
        self.assertEqual(ctx.session.states[1017], 3)
        self.assertEqual(ctx.session.personal, {})

    async def test_completed_drop_objective_is_not_repeated(self):
        ctx = context(quest=SimpleNamespace(id=1017))
        ctx.session.states[1017] = 3
        ctx.session.personal = {}
        ctx.inventory.counts[30301] = 4
        await objectives.drive_collect_drop(ctx, objective('collect_drop', (40336, 100, 30301, 4)))
        self.assertEqual(ctx.session.sent, [])

    async def test_casts_without_owned_items_are_not_collection_progress(self):
        ctx = context(quest=SimpleNamespace(id=1017))
        ctx.session.states[1017] = 3
        ctx.combat = SimpleNamespace(mobs={44: Mob(44, 40336, 'Mound', (0, 0))})
        ctx.scene.spawns = {1: dict(template=40336, interaction=5)}
        async def ack(name, predicate, timeout):
            return struct.pack('<HiiBB', 62034, 80, 44, 1, 0)
        ctx.session.expect = ack
        from unittest.mock import AsyncMock
        with patch('objectives.asyncio.sleep', new=AsyncMock()), patch('objectives.loot', new=AsyncMock()):
            with self.assertRaisesRegex(ProtocolError, 'gathering did not complete'):
                await objectives.drive_collect_drop(ctx, objective('collect_drop', (40336, 100, 30301, 4)))

    async def test_potion_uses_owned_item_and_waits_for_native_ready(self):
        from inventory import Inventory
        inventory = Inventory()
        inventory.add(0, 3, 30300)
        ctx = context(quest=SimpleNamespace(id=1014), inventory=inventory)
        ctx.combat = SimpleNamespace(player_id=50000003)
        ctx.session.states[1014] = 3
        async def send(name, payload=b''):
            if name == 'ItemUse':
                self.assertEqual(struct.unpack('<hhhIIHhhh', payload),
                                 (0, 0, 3, 50000003, 30300, 0, 0, 0, 0))
                ctx.session.states[1014] = READY
        ctx.send = send
        await objectives.drink_quest_potion(ctx, objective('buff', (1, 45134, 1)))
        self.assertEqual(ctx.session.waits[-1][1], READY)

    async def test_worker_uses_owned_hammer_and_requires_server_progress(self):
        from inventory import Inventory
        inventory = Inventory()
        inventory.add(0, 2, 30297)
        ctx = context(quest=SimpleNamespace(id=1010, return_npc=10213), inventory=inventory)
        ctx.session.states[1010] = 3
        ctx.combat = SimpleNamespace(mobs={44: Mob(44, 40338, 'Worker', (0, 0))})
        sent = []
        async def send(name, payload=b''):
            sent.append((name, payload))
            if name == 'ItemUse':
                self.assertEqual(struct.unpack('<hhhIIHhhh', payload), (0, 0, 2, 44, 30297, 0, 0, 0, 0))
                ctx.session.states[1010] = READY
        ctx.send = send
        with patch('objectives.asyncio.sleep', return_value=None):
            await objectives.drive_kill(ctx, objective('kill', (40338, 2, 0)))
        self.assertNotIn('MeleeAttack', [name for name, _ in sent])
        self.assertEqual([name for name, _ in sent][-1], 'ItemUse')

    async def test_worker_never_attacked_if_hammer_is_missing(self):
        from inventory import Inventory
        ctx = context(quest=SimpleNamespace(id=1010), inventory=Inventory())
        with self.assertRaisesRegex(ProtocolError, '30297'):
            await objectives.drive_kill(ctx, objective('kill', (40338, 2, 0)))


def _talker(actor):
    calls = []

    async def call(template):
        calls.append(template)
        return actor
    call.calls = calls
    return call


class ApproachTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_targets_do_not_walk(self):
        ctx = context(position=(0.0, 0.0))
        await objectives.approach(ctx, (1.0, 1.0), within=2.5)
        self.assertEqual(ctx.walk.calls, [])

    async def test_walk_uses_the_collision_safe_cell_when_a_grid_is_present(self):
        grid = SimpleNamespace(approach=lambda point: (5.0, 6.0))
        ctx = context(position=(0.0, 0.0), grid=grid)
        await objectives.approach(ctx, (4.0, 4.0), within=1.0)
        self.assertEqual(ctx.walk.calls, [((5.0, 6.0),)])

    async def test_missing_self_position_is_a_protocol_error(self):
        ctx = context()
        ctx.position = lambda: None
        with self.assertRaises(ProtocolError):
            await objectives.approach(ctx, (4.0, 4.0))


class FakeCombat:
    def __init__(self):
        self.mobs = {1: SimpleNamespace(position=(0.0, 0.0), alive=True,
                                        template=20289, name='Test')}
        self.kills = 0

    def hunting(self, template, position, radius=45):
        return 1


class DriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_hunt_uses_the_raw_sender_for_real_melee_packets(self):
        ctx = context(position=(0.0, 0.0))
        ctx.combat = FakeCombat()
        ctx.raw_send = _recorder('raw')
        seen = []

        async def engage(combat, send, target, timeout=45, report=print, spell=None, spell_interval=3.0, follow=None):
            seen.append((send, target))
            combat.kills += 1
            return True
        with patch.object(objectives, 'engage', engage):
            killed = await objectives.hunt(ctx, 20289, 1)
        self.assertEqual(killed, 1)
        self.assertEqual(seen, [(ctx.raw_send, 1)])

    async def test_hunt_counts_a_target_killed_by_an_authored_ally(self):
        ctx = context(quest=SimpleNamespace(id=2008, return_npc=10330), position=(0.0, 0.0))
        ctx.combat = FakeCombat()
        ctx.raw_send = _recorder('raw')

        async def engage(combat, send, target, timeout=45, report=print, spell=None, spell_interval=3.0, follow=None):
            combat.mobs[target].alive = False  # the authored ally group lands the last blow
            return True
        with patch.object(objectives, 'engage', engage):
            killed = await objectives.hunt(ctx, 20289, 1)
        self.assertEqual(killed, 1)

    async def test_hunt_stops_once_the_server_marks_the_quest_ready(self):
        ctx = context(quest=SimpleNamespace(id=2008, return_npc=10330), position=(0.0, 0.0))
        ctx.combat = FakeCombat()
        ctx.session.states[2008] = READY

        async def engage(combat, send, target, timeout=45, report=print, spell=None, spell_interval=3.0, follow=None):
            raise AssertionError('a ready quest must not attack')
        with patch.object(objectives, 'engage', engage):
            killed = await objectives.hunt(ctx, 20289, 1)
        self.assertEqual(killed, 0)

    async def test_hunt_stalls_are_retried_before_failing(self):
        ctx = context(position=(0.0, 0.0))
        ctx.combat = FakeCombat()
        calls = []

        async def engage(combat, send, target, timeout=60, report=print, spell=None,
                         spell_interval=3.0, follow=None):
            calls.append(follow)
            if len(calls) == 1:
                raise ProtocolError('swings never landed')
            combat.kills += 1
        with patch.object(objectives, 'engage', engage):
            killed = await objectives.hunt(ctx, 20289, 1)
        self.assertEqual(killed, 1)
        self.assertEqual(len(calls), 2)
        self.assertTrue(callable(calls[0]))

    async def test_follow_target_walks_only_when_out_of_reach(self):
        ctx = context(position=(0.0, 0.0))
        ctx.combat = FakeCombat()
        await objectives.follow_target(ctx, 1)
        self.assertEqual(ctx.walk.calls, [])
        ctx.combat.mobs[1].position = (5.0, 0.0)
        await objectives.follow_target(ctx, 1)
        self.assertEqual(ctx.walk.calls, [((5.0, 0.0),)])

    async def test_loot_uses_the_raw_sender_for_pickup_packets(self):
        ctx = context()
        ctx.raw_send = _recorder('raw')
        seen = []

        async def collect(combat, send, position, radius, timeout, report):
            seen.append((send, position))
            return [7]
        with patch.object(objectives, 'collect', collect):
            picked = await objectives.loot(ctx, radius=5)
        self.assertEqual(picked, [7])
        self.assertEqual(seen, [(ctx.raw_send, (0.0, 0.0))])

    async def test_kill_driver_uses_the_authored_template_and_count(self):
        ctx = context()
        runs = []

        async def hunt(context, template, count):
            runs.append((template, count))
        with patch.object(objectives, 'hunt', hunt):
            await objectives.drive_kill(ctx, objective('kill', (20289, 2, 0)))
        self.assertEqual(runs, [(20289, 2)])

    async def test_collect_drop_hunts_then_loots_once_per_item(self):
        ctx = context()
        ctx.session.personal = {}
        runs = []

        async def hunt(context, template, count):
            runs.append(('hunt', template, count))

        async def loot(context):
            runs.append(('loot',))
            key = (context.quest.id << 32) | (2 << 16) | 20289
            context.session.personal[key] = context.session.personal.get(key, 0) + 1
            return []
        with patch.object(objectives, 'hunt', hunt), patch.object(objectives, 'loot', loot):
            await objectives.drive_collect_drop(
                ctx, objective('collect_drop', (20289, 1, 0, 2)))
        self.assertEqual(runs, [('hunt', 20289, 1), ('loot',),
                                ('hunt', 20289, 1), ('loot',)])

    async def test_bare_talk_falls_back_to_the_returning_npc(self):
        ctx = context(quest=SimpleNamespace(id=1001, return_npc=10205))
        await objectives.drive_talk(ctx, objective('talk', ()))
        self.assertEqual(ctx.talk_to.calls, [10205])
        self.assertEqual(ctx.session.talked, [55])

    async def test_talk_selects_the_quests_dialog_entry(self):
        session = FakeSession(dialog=('1999', '1001'))
        ctx = context(session=session, quest=SimpleNamespace(id=1001, return_npc=10205))
        await objectives.drive_talk(ctx, objective('talk', ()))
        self.assertEqual(session.chosen, [1])

    async def test_travel_walks_to_the_authored_area(self):
        ctx = context(scene=FakeScene({351: (10.0, 20.0, 2.0)}))
        await objectives.drive_travel(ctx, objective('travel', (351,)))
        self.assertEqual(ctx.walk.calls, [((10.0, 20.0),)])

    async def test_unknown_travel_area_is_a_protocol_error(self):
        ctx = context()
        with self.assertRaises(ProtocolError):
            await objectives.drive_travel(ctx, objective('travel', (351,)))

    async def test_equip_performs_a_real_item_transfer(self):
        inventory = FakeInventory((0, 5))
        ctx = context(inventory=inventory)
        with patch.object(objectives, 'asyncio', SimpleNamespace(sleep=_no_sleep)):
            await objectives.drive_equip(ctx, objective('equip', (30275, 1, 1)))
        self.assertEqual([name for name, _ in ctx.session.sent],
                         ['LeaveShop', 'SwitchItemLocation'])
        self.assertEqual(inventory.discarded, [(0, 5)])

    async def test_equip_without_a_known_location_leaves_the_state_to_the_server(self):
        ctx = context(inventory=FakeInventory(None))
        await objectives.drive_equip(ctx, objective('equip', (30275, 1, 1)))
        self.assertEqual(ctx.session.sent, [])

    async def test_rejected_transfer_is_a_protocol_error(self):
        session = FakeSession()
        session.accept_ok = False
        ctx = context(session=session, inventory=FakeInventory((0, 5)))
        with patch.object(objectives, 'asyncio', SimpleNamespace(sleep=_no_sleep)):
            with self.assertRaises(ProtocolError):
                await objectives.drive_equip(ctx, objective('equip', (30275, 1, 1)))

    async def test_deliver_requires_the_npc_to_be_authored_on_this_map(self):
        ctx = context()
        with self.assertRaises(ProtocolError):
            await objectives.drive_deliver(ctx, objective('deliver', (10204, 100, 1)))


async def _no_sleep(*args, **kwargs):
    return None


class RunTests(unittest.IsolatedAsyncioTestCase):
    def quest(self, *kinds):
        return SimpleNamespace(id=9000, return_npc=10205,
                               objectives=tuple(objective(kind, ()) for kind in kinds))

    async def test_drivers_run_in_the_authored_order(self):
        ctx = context(quest=SimpleNamespace(id=9000, return_npc=10205))
        quest = self.quest('equip', 'talk')
        calls = []

        async def first(context, item):
            calls.append(item.kind)

        async def second(context, item):
            calls.append(item.kind)
            ctx.session.states[9000] = READY
        with patch.dict(objectives.DRIVERS, {'equip': first, 'talk': second}):
            await objectives.run(quest, ctx, timeout=.1)
        self.assertEqual(calls, ['equip', 'talk'])

    async def test_ready_quest_skips_the_remaining_objectives(self):
        ctx = context()
        ctx.session.states[9000] = READY
        with patch.dict(objectives.DRIVERS, {}, clear=True):
            await objectives.run(self.quest('kill'), ctx, timeout=.1)

    async def test_missing_driver_is_a_protocol_error(self):
        ctx = context()
        with patch.dict(objectives.DRIVERS, {}, clear=True):
            with self.assertRaises(ProtocolError):
                await objectives.run(self.quest('kill'), ctx, timeout=.1)

    async def test_ready_state_that_never_arrives_is_reported(self):
        ctx = context()
        quest = self.quest('level')

        async def wait(context, item):
            return None
        with patch.dict(objectives.DRIVERS, {'level': wait}):
            with self.assertRaises(ProtocolError):
                await objectives.run(quest, ctx, timeout=.05)


if __name__ == '__main__':
    unittest.main()
