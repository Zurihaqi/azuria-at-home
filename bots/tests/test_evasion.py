import asyncio
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from combat import Combat, Mob, engage
from evasion import Controller, Lane, escape, warning


CAST = bytes.fromhex('f4e2dc8affff82f0fa020181c1afbebe71703f0000000001')
BOSS = 4294937308


class GeometryTests(unittest.TestCase):
    def test_recorded_native_warning_uses_direction_and_caster_position(self):
        mobs = {BOSS: Mob(BOSS, 41165, 'Keda', (22, 87.57))}
        lane = warning(CAST, mobs, 100)
        self.assertEqual(lane.caster, BOSS)
        self.assertEqual(lane.expires, 103.25)
        self.assertTrue(lane.contains((21.75, 88.25)))
        self.assertAlmostEqual(sum(v*v for v in lane.direction), 1)

    def test_unknown_unmarked_malformed_and_nonfinite_casts_are_ignored(self):
        mobs = {BOSS: Mob(BOSS, 41165, 'Keda', (22, 87.57))}
        for payload in (CAST[:-1], CAST[:-1]+b'\0', b'\x91\xe2'+CAST[2:],
                        struct.pack('<HIIBfffB', 58100, BOSS, 1, 1, float('nan'), 1, 0, 1),
                        struct.pack('<HIIBfffB', 58100, BOSS, 1, 1, 0, 0, 0, 1)):
            self.assertIsNone(warning(payload, mobs, 100))

    def test_escape_is_outside_lane_and_cannot_cross_a_wall(self):
        lane = Lane(BOSS, (0, 0), (1, 0), 10)
        grid = SimpleNamespace(approach=lambda p: p, line_clear=lambda a,b: b[1] > 0)
        point = escape(lane, (1, 0), grid)
        self.assertEqual(point, (1, 6))
        self.assertFalse(lane.contains(point))
        grid.line_clear = lambda a,b: False
        self.assertIsNone(escape(lane, (1, 0), grid))
        self.assertIsNone(escape(lane, (1, 0), None))


class AvoidanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_movement_must_leave_lane_before_success_is_reported(self):
        position = [(21.75, 88.25)]
        async def walk(point): position[0] = point
        ctx = SimpleNamespace(combat=SimpleNamespace(mobs={BOSS: Mob(BOSS, 41165, '', (22,87.57))}),
            position=lambda: position[0], grid=SimpleNamespace(approach=lambda p:p, line_clear=lambda a,b:True), walk=walk)
        events = []
        controller = Controller(ctx, emit=lambda *a: events.append(a), clock=lambda:100)
        controller.observe('SpellCast', CAST)
        self.assertTrue(controller.event.is_set())
        with patch('evasion.asyncio.sleep', new=AsyncMock()):
            await controller.avoid()
        self.assertFalse(controller.event.is_set())
        self.assertTrue(any('confirmed outside' in msg for _,msg in events))

    async def test_warning_interrupts_attack_wait_and_serializes_escape_then_follow(self):
        root = Path(__file__).resolve().parents[1]
        state = Combat(json.loads((root/'protocol/zone.json').read_text()), 50000002)
        state.mobs[BOSS] = Mob(BOSS,41165,'Keda',(0,0))
        event = asyncio.Event()
        order = []
        async def attack(*args):
            order.append('attack')
            try:
                event.set()
                await asyncio.sleep(100)
            finally: order.append('attack cancelled')
        async def avoid():
            self.assertEqual(order[-1], 'attack cancelled')
            order.append('dodge')
            event.clear()
        async def follow(target):
            order.append('follow')
            state.mobs[target].alive=False
        state.evasion=SimpleNamespace(event=event,avoid=avoid)
        with patch('combat._engage', side_effect=attack):
            self.assertTrue(await engage(state,AsyncMock(),BOSS,timeout=2,follow=follow))
        self.assertEqual(order,['attack','attack cancelled','dodge','follow'])


if __name__ == '__main__': unittest.main()
