import asyncio
from pathlib import Path
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assist import Assist, resource_templates, hostile_templates
from combat import Mob, engage
from party import Member, Party


class AssistTests(unittest.TestCase):
    def test_native_biology_classification_separates_resources_from_hostiles(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'S_Biology.ini'
            path.write_text('header\n40337||||||5||1|\n40323||||||2||1|\n41165||||||3||7|\n10220||||||1||8|\n')
            self.assertEqual(resource_templates(path),frozenset({40337}))
            self.assertEqual(hostile_templates(path),frozenset({40323}))

    def setUp(self):
        self.party = Party()
        self.party.members = {0: Member(0, 11, 'Arden'), 1: Member(1, 22, 'Human')}
        self.party.leader = 22
        self.party.positions[22] = (2, 10, 10, 100)
        self.combat = SimpleNamespace(mobs={44: Mob(44, 40323, 'Rabbit', (12, 10))})
        self.assist = Assist({40323})

    def attack(self, actor=22, victim=44):
        self.assist.observe('MeleeAttack', struct.pack('<IIihhh', actor, victim, 3, 0, 0, 0),
                            self.party.leader, now=100)

    def target(self, now=101):
        return self.assist.target(self.party, self.combat, 2, (10, 11), now=now)

    def test_live_leader_target_only(self):
        self.attack(actor=99)
        self.assertIsNone(self.target())
        self.attack()
        self.assertEqual(self.target(), 44)
        self.assertIsNone(self.target(now=108))

    def test_never_attack_npc_or_party_member(self):
        self.attack()
        self.combat.mobs[44].template = 10210
        self.assertIsNone(self.target())
        self.combat.mobs[44].template = 40323
        self.party.members[2] = Member(2, 44, 'Player')
        self.assertIsNone(self.target())

    def test_death_visibility_leadership_map_and_range_stop_assist(self):
        self.attack()
        self.combat.mobs[44].alive = False
        self.assertIsNone(self.target())
        self.combat.mobs[44].alive = True
        self.party.leader = 11
        self.assertIsNone(self.target())
        self.party.leader = 22
        self.party.positions[22] = (3, 10, 10, 100)
        self.assertIsNone(self.target())
        self.party.positions[22] = (2, 100, 100, 100)
        self.assertIsNone(self.target())
        self.party.positions[22] = (2, 10, 10, 100)
        self.combat.mobs.clear()
        self.assertIsNone(self.target())

    def test_verified_spell_shape_and_malformed_packets(self):
        self.assist.observe('SpellHitToLife', struct.pack('<HII', 51401, 22, 44) + bytes(14), 22, now=100)
        self.assertEqual(self.target(), 44)
        self.assist.intent = None
        for payload in (b'', bytes(10), bytes(25)):
            self.assist.observe('SpellHitToLife', payload, 22, now=100)
        self.assertIsNone(self.target())

    def test_selected_target_can_be_assisted_before_first_hit(self):
        self.assertEqual(self.assist.query(22, 2, now=100), struct.pack('<I', 22))
        self.assist.selected(struct.pack('<IBI', 44, 1, 0), 22, 2, now=100.1)
        self.assertEqual(self.target(), 44)
        self.assist.query(22, 2, now=101)
        self.assist.selected(struct.pack('<IBI', 0, 1, 0), 22, 2, now=101.1)
        self.assertIsNone(self.target(now=102))

    def test_target_reply_requires_fresh_matching_query(self):
        reply = struct.pack('<IBI', 44, 1, 0)
        self.assist.selected(reply, 22, 2, now=100)
        self.assertIsNone(self.target())
        self.assist.query(22, 2, now=100)
        self.assist.selected(reply, 11, 2, now=100.1)
        self.assertIsNone(self.target())
        self.assist.query(22, 2, now=100)
        self.assist.selected(reply, 22, 3, now=100.1)
        self.assertIsNone(self.target())
        self.assist.query(22, 2, now=100)
        self.assist.selected(reply, 22, 2, now=103)
        self.assertIsNone(self.target())


class AssistedRecordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_assisted_fights_do_not_train_solo_policy(self):
        tracker = SimpleNamespace(begin=lambda *a: self.fail('Assisted fight recorded as solo'),
                                  finish=lambda *a: self.fail('Unexpected observation closure'))
        combat = SimpleNamespace(learning=tracker, mobs={44: Mob(44, 40323, 'Rabbit', (0, 0))})
        with patch('combat._engage', new=AsyncMock(return_value=True)) as inner:
            self.assertTrue(await engage(combat, AsyncMock(), 44, record=False))
            inner.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
