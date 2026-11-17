import asyncio
import json
import math
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from combat import Cadence, Combat, Mob, collect, engage
from wire import ProtocolError, string

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / 'protocol/zone.json').read_text())
PLAYER = 50000003


def see_mob(mob_id, template, x, y, name='Test Mob'):
    return (struct.pack('<IHb', mob_id, template, 0)
            + struct.pack('<fffff', x, y, 0.0, 0.0, 1.0)
            + struct.pack('<bI', 0, 0) + string(name))


def melee(attacker, victim, damage=12, hurt=0):
    # Current ZoneServer appends HurtActionID; the older five-field shape is
    # still tolerated by the parser.
    return struct.pack('<IIihh', attacker, victim, damage, 0, 0) + struct.pack('<h', hurt)


def die(victim, killer, flags=0, revive=0):
    return struct.pack('<IIBH', victim, killer, flags, revive)


def see_treasure(ident, x, y):
    return (struct.pack('<Iffff', ident, x, y, 0.0, 0.0)
            + struct.pack('<HhI', 0, 0, 0) + struct.pack('<hbib', 0, 0, 0, 0))


def pickup_ok(ident):
    return struct.pack('<IHIhhh', ident, 1, 0, 0, 0, 0)


def combat():
    return Combat(PROTOCOL, PLAYER)


class ObservationTests(unittest.TestCase):
    def test_prediction_refreshes_current_position_without_using_future_destination(self):
        state = combat()
        state.mobs[42] = Mob(42, 40323, 'Roamer', (1, 1))
        packet = struct.pack('<IHHHHHHIIiii', 42, 3200, 4800, 0, 1,
                             4000, 5600, 0, 0, 0, 0, 0)
        state.observe(PROTOCOL['CNC_CZ_ClientMovePrediction'], packet)
        self.assertEqual(state.mobs[42].position, (200, 300))

    def test_world_state_starts_empty(self):
        state = combat()
        self.assertEqual((state.mobs, state.treasures, state.target), ({}, {}, None))

    def test_see_mob_registers_template_and_position(self):
        state = combat()
        state.observe(state.see_mob, see_mob(900, 20289, 10.5, 20.25))
        self.assertEqual(state.mobs[900], Mob(900, 20289, 'Test Mob', (10.5, 20.25)))

    def test_truncated_see_mob_is_ignored(self):
        state = combat()
        self.assertEqual(state.observe(state.see_mob, b'\x01\x02'), [])
        self.assertEqual(state.mobs, {})

    def test_non_finite_see_mob_is_ignored(self):
        state = combat()
        state.observe(state.see_mob, see_mob(900, 20289, math.inf, 0))
        self.assertEqual(state.mobs, {})

    def test_only_own_melee_counts_as_an_acknowledgement(self):
        state = combat()
        state.observe(state.melee_attack, melee(PLAYER + 1, 900))
        self.assertEqual(state.acks, 0)
        events = state.observe(state.melee_attack, melee(PLAYER, 900))
        self.assertEqual(state.acks, 1)
        self.assertIn('900', events[0])

    def test_legacy_sixteen_byte_melee_is_still_acknowledged(self):
        state = combat()
        legacy = struct.pack('<IIihh', PLAYER, 900, 7, 0, 0)
        self.assertEqual(len(legacy), 16)
        state.observe(state.melee_attack, legacy)
        self.assertEqual(state.acks, 1)

    def test_die_marks_the_mob_dead_and_reports_a_kill(self):
        state = combat()
        state.observe(state.see_mob, see_mob(900, 20289, 0, 0))
        events = state.observe(state.die, die(900, PLAYER))
        self.assertFalse(state.mobs[900].alive)
        self.assertTrue(events[0].startswith('Killed'))

    def test_someone_elses_kill_is_not_our_progress(self):
        state = combat()
        state.observe(state.see_mob, see_mob(900, 20289, 0, 0))
        state.observe(state.die, die(900, PLAYER + 1))
        self.assertFalse(state.mobs[900].alive)
        self.assertEqual(state.target, None)

    def test_own_death_clears_the_selected_target(self):
        state = combat()
        state.target = 900
        state.observe(state.die, die(PLAYER, 900))
        self.assertIsNone(state.target)

    def test_treasure_lifecycle(self):
        state = combat()
        state.observe(state.see_treasure, see_treasure(77, 3.5, 4.5))
        self.assertEqual(state.treasures[77], (3.5, 4.5))
        state.observe(state.pickup_ok, pickup_ok(77))
        self.assertEqual(state.treasures, {})
        self.assertEqual(state.pickup_acks, [77])

    def test_treasure_can_disappear_without_being_taken(self):
        state = combat()
        state.observe(state.see_treasure, see_treasure(77, 0, 0))
        state.observe(state.treasure_gone, struct.pack('<I', 77))
        self.assertEqual(state.treasures, {})
        self.assertEqual(state.pickup_acks, [])

    def test_move_char_updates_mobs_and_counts_self_reports(self):
        state = combat()
        state.observe(state.see_mob, see_mob(900, 20289, 0, 0))
        state.observe(state.move_char, struct.pack('<iff', 900, 4.0, 5.0))
        state.observe(state.move_char, struct.pack('<iff', PLAYER, 1.0, 2.0))
        self.assertEqual(state.mobs[900].position, (4.0, 5.0))
        self.assertEqual(state.self_reports, 1)

    def test_reset_drops_actors_and_loot(self):
        state = combat()
        state.observe(state.see_mob, see_mob(900, 20289, 0, 0))
        state.observe(state.see_treasure, see_treasure(77, 0, 0))
        state.target = 900
        state.reset()
        self.assertEqual((state.mobs, state.treasures, state.target), ({}, {}, None))


class QueryTests(unittest.TestCase):
    def test_nearest_skips_dead_and_distant_mobs(self):
        state = combat()
        state.observe(state.see_mob, see_mob(1, 20289, 20, 0))
        state.observe(state.see_mob, see_mob(2, 20289, 2, 0))
        state.observe(state.see_mob, see_mob(3, 12345, 1, 0))
        self.assertEqual(state.nearest(20289, (0, 0)).id, 2)
        state.observe(state.die, die(2, PLAYER))
        self.assertEqual(state.nearest(20289, (0, 0)).id, 1)
        self.assertIsNone(state.nearest(20289, (0, 0), radius=1))
        self.assertIsNone(state.nearest(777, (0, 0)))

    def test_nearest_without_a_reported_position_is_none(self):
        state = combat()
        state.observe(state.see_mob, see_mob(1, 20289, 20, 0))
        self.assertIsNone(state.nearest(20289, None))

    def test_hunting_re_resolves_after_a_kill(self):
        state = combat()
        state.observe(state.see_mob, see_mob(1, 20289, 5, 0))
        state.observe(state.see_mob, see_mob(2, 20289, 9, 0))
        self.assertEqual(state.hunting(20289, (0, 0)), 1)
        state.observe(state.die, die(1, PLAYER))
        self.assertEqual(state.hunting(20289, (0, 0)), 2)
        state.observe(state.die, die(2, PLAYER))
        self.assertIsNone(state.hunting(20289, (0, 0)))


class PayloadTests(unittest.TestCase):
    def test_outbound_shapes(self):
        state = combat()
        self.assertEqual(state.target_payload(900), struct.pack('<i', 900))
        self.assertEqual(state.attack_payload(900), struct.pack('<ib', 900, 0))
        self.assertEqual(state.pickup_payload(77), struct.pack('<I', 77))

    def test_actor_ids_above_int32_are_accepted(self):
        # Node actors arrive with 0xFFFF.... ids, which do not fit a signed int.
        state = combat()
        actor = 4294942125
        self.assertEqual(state.target_payload(actor), struct.pack('<I', actor))
        self.assertEqual(state.attack_payload(actor), struct.pack('<IB', actor, 0))

    def test_missing_protocol_names_are_rejected_early(self):
        with self.assertRaises(ProtocolError):
            Combat({}, PLAYER)


class CadenceTests(unittest.TestCase):
    def test_rejection_backs_off_and_success_creeps_down(self):
        cadence = Cadence(1.0)
        cadence.rejected()
        self.assertEqual(cadence.interval, 1.5)
        for _ in range(4):
            cadence.accepted()
        self.assertAlmostEqual(cadence.interval, 1.425)

    def test_interval_is_clamped(self):
        cadence = Cadence(1.0)
        for _ in range(20):
            cadence.rejected()
        self.assertEqual(cadence.interval, Cadence.MAXIMUM)
        for _ in range(400):
            cadence.accepted()
        self.assertEqual(cadence.interval, Cadence.MINIMUM)


class Server:
    """Minimal stand-in for the zone: acks attacks and kills the mob on schedule."""

    def __init__(self, state, kill_after=2, attacks_before_reply=0):
        self.state, self.kill_after, self.attacks_before_reply = state, kill_after, attacks_before_reply
        self.sent, self.attacks = [], 0

    async def __call__(self, opcode, payload=b''):
        self.sent.append((opcode, payload))
        if opcode != PROTOCOL['CNE_CZ_ZoneServerMeleeAttack']:
            return
        self.attacks += 1
        if self.attacks <= self.attacks_before_reply:
            return
        victim, = struct.unpack_from('<i', payload)
        self.state.observe(self.state.melee_attack, melee(PLAYER, victim))
        if self.attacks >= self.kill_after:
            self.state.observe(self.state.die, die(victim, PLAYER))


class EngagementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = combat()
        self.state.cadence.interval = .01
        self.state.observe(self.state.see_mob, see_mob(900, 20289, 3, 4))

    async def test_engage_targets_first_then_strikes_until_the_mob_dies(self):
        server = Server(self.state)
        self.assertTrue(await engage(self.state, server, 900, timeout=5, report=lambda *a, **k: None))
        opcodes = [opcode for opcode, _ in server.sent]
        self.assertEqual(opcodes[0], PROTOCOL['CNE_CZ_ZoneServerTargetUpdate'])
        self.assertEqual(opcodes[1], PROTOCOL['CNE_CZ_ZoneServerMeleeAttack'])
        self.assertEqual(self.state.target, 900)
        self.assertFalse(self.state.mobs[900].alive)

    def enable_recording(self):
        from encounter_learning import Tracker
        class MemoryStore:
            def __init__(self):
                self.rows = []
            def record(self, **row):
                self.rows.append(row)
        store = MemoryStore()
        tracker = Tracker(store, PROTOCOL)
        tracker.map_id, tracker.level, tracker.capability = 2, 6, 'fixture:melee'
        self.state.learning = tracker
        self.state.mobs[900].template = 40323
        return store

    async def test_native_engagement_records_a_kill_without_altering_packets(self):
        store = self.enable_recording()
        server = Server(self.state)
        await engage(self.state, server, 900, timeout=5, report=lambda *a, **k: None)
        self.assertEqual([row['outcome'] for row in store.rows], ['kill'])
        self.assertGreater(store.rows[0]['damage_out'], 0)
        self.assertEqual(server.sent[0][0], PROTOCOL['CNE_CZ_ZoneServerTargetUpdate'])

    async def test_cancelled_engagement_is_censored_not_a_death(self):
        store = self.enable_recording()
        server = Server(self.state, kill_after=1000)
        task = asyncio.create_task(engage(self.state, server, 900, timeout=5,
                                          report=lambda *a, **k: None))
        await asyncio.sleep(.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual([row['outcome'] for row in store.rows], ['interrupted'])

    async def test_unacknowledged_attacks_back_the_cadence_off(self):
        server = Server(self.state, kill_after=3, attacks_before_reply=1)
        await engage(self.state, server, 900, timeout=5, report=lambda *a, **k: None)
        self.assertGreater(self.state.cadence.interval, .01)

    async def test_unacknowledged_swings_follow_and_reselect_the_victim(self):
        server = Server(self.state, kill_after=3, attacks_before_reply=2)
        followed = []

        async def follow(target):
            followed.append(target)

        self.assertTrue(await engage(self.state, server, 900, timeout=5,
                                     report=lambda *a, **k: None, follow=follow))
        self.assertEqual(followed, [900])
        selections = [payload for opcode, payload in server.sent
                      if opcode == PROTOCOL['CNE_CZ_ZoneServerTargetUpdate']]
        self.assertEqual(selections, [struct.pack('<I', 900)] * 2)

    async def test_already_dead_target_returns_immediately(self):
        self.state.observe(self.state.die, die(900, PLAYER))
        server = Server(self.state)
        self.assertTrue(await engage(self.state, server, 900, timeout=5, report=lambda *a, **k: None))
        self.assertEqual(server.sent, [])

    async def test_engage_casts_the_weapon_spell_between_melee_swings(self):
        server = Server(self.state)
        await engage(self.state, server, 900, timeout=5, report=lambda *a, **k: None,
                     spell=45113)
        casts = [payload for opcode, payload in server.sent
                 if opcode == PROTOCOL['CNE_CZ_ZoneServerSpellCastToLife']]
        self.assertEqual(casts, [struct.pack('<HIH', 45113, 900, 0)])
        self.assertLess(server.sent.index((PROTOCOL['CNE_CZ_ZoneServerSpellCastToLife'],
                                          casts[0])),
                        server.sent.index((PROTOCOL['CNE_CZ_ZoneServerMeleeAttack'],
                                           struct.pack('<IB', 900, 0))))

    async def test_unknown_target_is_a_protocol_error(self):
        with self.assertRaises(ProtocolError):
            await engage(self.state, Server(self.state), 404, timeout=1, report=lambda *a, **k: None)

    async def test_engage_times_out_when_the_mob_never_dies(self):
        self.state.cadence.interval = .01
        with self.assertRaises(ProtocolError):
            await engage(self.state, Server(self.state, kill_after=10 ** 6), 900, timeout=.2,
                         report=lambda *a, **k: None)


class LootTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_takes_nearby_treasure_only(self):
        state = combat()
        state.observe(state.see_treasure, see_treasure(1, 1, 1))
        state.observe(state.see_treasure, see_treasure(2, 20, 20))

        async def send(opcode, payload=b''):
            if opcode == PROTOCOL['CNE_CZ_ZoneServerTreasurePickup']:
                ident, = struct.unpack('<I', payload)
                state.observe(state.pickup_ok, pickup_ok(ident))

        picked = await collect(state, send, (0, 0), radius=4, timeout=2, report=lambda *a, **k: None)
        self.assertEqual(picked, [1])
        self.assertEqual(set(state.treasures), {2})

    async def test_unconfirmed_pickup_is_reported_and_retried_later(self):
        state = combat()
        state.observe(state.see_treasure, see_treasure(1, 1, 1))
        picked = await collect(state, lambda *a: asyncio.sleep(0), (0, 0),
                               radius=4, timeout=.05, report=lambda *a, **k: None)
        self.assertEqual(picked, [])
        self.assertEqual(set(state.treasures), {1})


if __name__ == '__main__':
    unittest.main()
