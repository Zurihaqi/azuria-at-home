import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content import parse_quests
from npc import ACTIVE, FINISHED, READY
from quests import (active, condition_holds, finishable, next_offer, objective_plan,
                    offer_at, offers, progress_by_kind, supported, turn_in_npc, unlocked)

ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT.parent / 'staging/ultimate/hxsy/Data/db/S_Mission.ini'
if not MISSION.exists():
    MISSION = ROOT / 'maps/S_Mission.ini'


def quests():
    return parse_quests(MISSION)


class ConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = quests()

    def test_fms_is_an_or_over_the_authored_chain(self):
        condition = self.table[1001].conditions[0]
        self.assertTrue(condition_holds(condition, {2001: FINISHED}, 1, 1))
        self.assertTrue(condition_holds(condition, {1000: FINISHED}, 1, 1))
        self.assertFalse(condition_holds(condition, {2001: ACTIVE}, 1, 1))
        self.assertFalse(condition_holds(condition, {}, 1, 1))

    def test_char_level_operations(self):
        condition = self.table[2001].conditions[1]
        self.assertEqual((condition.name, condition.args), ('If_CharLevel', ('2', '1')))
        self.assertTrue(condition_holds(condition, {}, 1, 1))
        self.assertFalse(condition_holds(condition, {}, 2, 1))

    def test_char_level_exp_is_a_floor(self):
        hidden = self.table[2563].conditions[0]
        self.assertEqual(hidden.name, 'If_CharLevelExp')
        self.assertFalse(condition_holds(hidden, {}, 1, 1))
        self.assertFalse(condition_holds(hidden, {}, 98, 1))
        self.assertTrue(condition_holds(hidden, {}, 99, 1))

    def test_weapon_conditions(self):
        weapon = self.table[2001].conditions[0]
        self.assertTrue(condition_holds(weapon, {}, 1, 1))
        self.assertFalse(condition_holds(weapon, {}, 1, 0))
        self.assertTrue(condition_holds(weapon, {}, 1, None))

        staves = next(condition for condition in self.table[1578].conditions
                      if condition.name == 'If_CheckNotWeapon')
        self.assertEqual(staves.name, 'If_CheckNotWeapon')
        self.assertFalse(condition_holds(staves, {}, 1, 1))
        self.assertTrue(condition_holds(staves, {}, 1, 12))

    def test_unknown_conditions_defer_to_the_server(self):
        gender = next(condition for quest in self.table.values()
                      for condition in quest.conditions if condition.name == 'If_Gender')
        self.assertTrue(condition_holds(gender, {}, 1, None))


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = quests()
        cls.npcs = {0, 10204, 10205, 10330}

    def test_unlocked_combines_every_condition(self):
        starter = self.table[2001]
        self.assertTrue(unlocked(starter, {}, 1, 1))
        self.assertFalse(unlocked(starter, {}, 1, 0))
        self.assertFalse(unlocked(starter, {}, 0, 1))

    def test_supported_requires_a_driver_for_every_objective(self):
        self.assertTrue(supported(self.table[2001]))
        self.assertTrue(supported(self.table[2008]))
        self.assertTrue(supported(self.table[1005]))

    def test_finishable_skips_in_flight_and_finished_quests(self):
        starter = self.table[2001]
        self.assertTrue(finishable(starter, {}, 1, 1, 610))
        self.assertFalse(finishable(starter, {2001: ACTIVE}, 1, 1, 610))
        self.assertFalse(finishable(starter, {2001: READY}, 1, 1, 610))
        self.assertFalse(finishable(starter, {2001: FINISHED}, 1, 1, 610))

    def test_mission_board_quests_are_map_scoped(self):
        hidden = self.table[2563]
        self.assertEqual((hidden.accept_npc, hidden.node), (0, 0))
        self.assertTrue(finishable(hidden, {}, 99, 1))
        self.assertFalse(finishable(hidden, {}, 99, 1, 610))

    def test_offers_prefer_the_main_line_and_are_reachable(self):
        result = offers(self.table, {}, 1, 1, self.npcs, 610)
        self.assertEqual(result[0].id, 2001)
        self.assertTrue(all(quest.accept_npc in self.npcs for quest in result))
        self.assertNotIn(2563, [quest.id for quest in result])

    def test_offer_at_filters_by_npc(self):
        result = offer_at(self.table, 10204, {2001: FINISHED}, 1, 1, 610)
        self.assertEqual(result[0].id, 1001)
        self.assertTrue(all(quest.accept_npc == 10204 for quest in result))

    def test_next_offer_prefers_the_chain_behind_the_last_quest(self):
        after = self.table[2001]
        result = next_offer(self.table, {2001: FINISHED}, 1, 1, self.npcs, after, 610)
        self.assertEqual(result.id, 1001)
        fresh = next_offer(self.table, {}, 1, 1, self.npcs, None, 610)
        self.assertEqual(fresh.id, 2001)

    def test_turn_in_npc_falls_back_to_the_accepting_npc(self):
        self.assertEqual(turn_in_npc(self.table[1001]), 10205)
        self.assertEqual(turn_in_npc(self.table[2001]), 10204)

    def test_active_lists_ready_quests_first(self):
        statuses = {2001: ACTIVE, 1001: READY, 1002: ACTIVE}
        self.assertEqual([quest.id for quest in active(self.table, statuses)],
                         [1001, 1002, 2001])

    def test_objective_plan_carries_the_quest_and_index(self):
        plan = objective_plan(self.table[2008])
        self.assertEqual([item.index for item in plan], [0, 1, 2])
        self.assertEqual({item.quest for item in plan}, {2008})
        self.assertEqual([item.kind for item in plan], ['kill', 'kill', 'kill'])

    def test_progress_by_kind_counts_authored_objectives(self):
        self.assertEqual(progress_by_kind(self.table[2008]), {'kill': 3})
        self.assertEqual(progress_by_kind(self.table[2001]), {'equip': 1})


if __name__ == '__main__':
    unittest.main()
