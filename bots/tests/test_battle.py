import asyncio
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from battle import Controller, learned_skills, player_stats, upgrade_candidates
from item_stream import Item
from wire import ProtocolError, string


def stats(hp=400, secondary=351):
    return (struct.pack('<I', 50000003) + string('Arden') + string('') * 3 +
            struct.pack('<fB', 8.6, 0) + bytes(4) + struct.pack('<Hii', 8, hp, secondary))


class SnapshotTests(unittest.TestCase):
    def test_secondary_prefix_integer_is_not_assumed_maximum_hp(self):
        data = player_stats(stats(hp=678))
        self.assertEqual(data['hp'], 678)
        self.assertIsNone(data['maximum_hp'])

    def test_learned_skills_require_complete_native_tail(self):
        payload = struct.pack('<BbIhHBHBh', 1, 0, 0, 2, 51401, 8, 51402, 0, 6) + bytes(12)
        gear, skills = learned_skills(payload)
        self.assertEqual(gear, {})
        self.assertEqual(skills, {51401: 8, 51402: 0})
        with self.assertRaises(ProtocolError): learned_skills(payload[:-1])

    def test_gear_selection_requires_owned_eligible_strict_upgrade(self):
        catalog = {'10001':dict(type=8,level=1,score=113), '10002':dict(type=8,level=8,score=200),
                   '10003':dict(type=8,level=18,score=400), '10004':dict(type=8,level=1,score=100)}
        worn = {(0, 5): Item(10001)}
        bag = {(0, 0): Item(10002), (0, 1): Item(10003), (0, 2): Item(10004), (0, 3): Item(99999)}
        self.assertEqual(upgrade_candidates(bag, worn, catalog, 8), [(87, (0, 0), 10002)])
        self.assertEqual(upgrade_candidates({}, worn, catalog, 99), [])


class BattleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cast_waits_for_native_ack_and_uses_only_learned_allowlisted_skill(self):
        controller = Controller()
        controller.learned = {51401: 8, 51402: 0, 99999: 99}
        sent = []
        async def send(name, payload):
            sent.append((name, payload))
            spell, target, _ = struct.unpack('<HIH', payload)
            controller.observe('SpellCastOK', struct.pack('<HiiBB', spell, 10, target, 1, 0))
        with patch('battle.asyncio.sleep', new=AsyncMock()):
            self.assertTrue(await controller.action(send, 123))
        self.assertEqual(sent, [('SpellCastToLife', struct.pack('<HIH', 51401, 123, 0))])
        self.assertFalse(await controller.action(send, 123))
        self.assertEqual(len(sent), 1)

    async def test_transient_native_rejection_retries_after_backoff(self):
        now = [100.0]
        controller = Controller(clock=lambda: now[0])
        controller.learned = {51401: 1}
        async def send(name, payload):
            controller.observe('CommandFailReturn', struct.pack('<ii', 74, 51401))
        self.assertFalse(await controller.action(send, 123))
        self.assertNotIn(51401, controller.disabled)
        self.assertFalse(await controller.action(send, 123))
        self.assertEqual(controller.cast_failures[51401], 1)
        now[0] += 20
        async def accepted(name, payload):
            controller.observe('SpellCastOK', struct.pack('<HiiBB', 51401, 0, 123, 1, 0))
        with patch('battle.asyncio.sleep', new=AsyncMock()):
            self.assertTrue(await controller.action(accepted, 123))
        self.assertNotIn(51401, controller.cast_failures)

    async def test_potion_uses_only_owned_stack_and_requires_native_consumption(self):
        now = [100.0]
        controller = Controller(clock=lambda: now[0])
        controller.stats = dict(actor=50000003, hp=100)
        controller.bag = {(0, 1): Item(10534, 10)}
        async def refresh(send, fields=('stats',)):
            pass
        controller.refresh = refresh
        sent = []
        async def send(name, payload):
            sent.append((name, payload))
            controller.bag[(0, 1)].durability -= 1
        with patch('battle.asyncio.sleep', new=AsyncMock()):
            await controller.use_owned_potion(send)
            await controller.use_owned_potion(send)
        self.assertEqual(len(sent), 1)
        self.assertEqual(struct.unpack('<hhhIIHhhh', sent[0][1]),
                         (0, 0, 1, 50000003, 10534, 0, 0, 0, 0))
        self.assertEqual(controller.bag[(0, 1)].durability, 9)
        controller.bag.clear()
        now[0] += 20
        await controller.use_owned_potion(send)
        self.assertEqual(len(sent), 1)

    async def test_unrelated_ack_does_not_confirm_a_cast(self):
        controller = Controller()
        future = asyncio.get_running_loop().create_future()
        controller.pending_cast = (51401, 123, future)
        controller.observe('SpellCastOK', struct.pack('<HiiBB', 51402, 10, 123, 1, 0))
        self.assertFalse(future.done())
        future.cancel()

    async def test_cancelled_cast_clears_pending_state(self):
        controller = Controller()
        controller.learned = {51401: 1}
        async def send(*args): raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await controller.action(send, 123)
        self.assertIsNone(controller.pending_cast)

    async def test_owned_upgrade_must_be_confirmed_by_equipment_refresh(self):
        catalog = {'10001':dict(type=8,level=1,score=113), '10002':dict(type=8,level=8,score=200)}
        controller = Controller(catalog=catalog)
        controller.stats = dict(hp=400, level=8)
        controller.worn = {(0,5):Item(10001)}
        controller.bag = {(0,2):Item(10002)}
        calls = []
        async def refresh(send, fields=('stats',)):
            if fields == ('gear', 'bag'):
                controller.worn = {(0,5):Item(10002)}
        controller.refresh = refresh
        async def send(name, payload=b''):
            calls.append(name)
            if name == 'SwitchItemLocation':
                controller.observe('SwitchItemLocationOK', struct.pack('<hhhhhhB', 0, 2, 0, 1, 5, 0, 1))
        await controller.prepare(send)
        self.assertIn('SwitchItemLocation', calls)
        self.assertEqual(controller.worn[(0,5)].id, 10002)


if __name__ == '__main__': unittest.main()
