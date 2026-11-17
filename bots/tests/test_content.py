import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content import (Scene, accept_actions, conditions, display_items, objectives,
                     parse_quests, quest_catalog, rewards, segments)
from wire import ProtocolError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / 'staging/ultimate/hxsy/Data'
MISSION = DATA / 'db/S_Mission.ini'
SCENE = DATA / 'scene/S610.ini'
if not MISSION.exists():
    MISSION = ROOT / 'maps/S_Mission.ini'
if not SCENE.exists():
    SCENE = ROOT / 'maps/S610.ini'


def quests():
    return parse_quests(MISSION)


class ScriptParsingTests(unittest.TestCase):
    def test_blank_slots_are_dropped(self):
        self.assertEqual(segments('#:NPCTalk :::::::'), ['NPCTalk'])
        self.assertEqual(segments('#:A 1:######:B 2'), ['A 1', 'B 2'])

    def test_objective_kinds_are_normalised(self):
        parsed = objectives('MonsterKilled 20289 1 0:NPCTalk :EquipItem 30275 1 1')
        self.assertEqual([item.kind for item in parsed], ['kill', 'talk', 'equip'])
        self.assertEqual(parsed[0].args, (20289, 1, 0))
        self.assertEqual(parsed[1].args, ())
        self.assertEqual(parsed[0].command, 'MonsterKilled')

    def test_non_numeric_objective_is_kept_unsupported(self):
        parsed = objectives('AreaTravel 00351:MonsterKilled boss 1')
        self.assertEqual(parsed[0].kind, 'travel')
        self.assertEqual(parsed[0].args, (351,))
        self.assertEqual(parsed[1], objectives('MonsterKilled boss 1')[0])
        self.assertEqual(parsed[1].kind, 'unsupported')
        self.assertEqual(parsed[1].command, 'MonsterKilled')

    def test_conditions_keep_the_or_list_as_one_argument(self):
        parsed = conditions('If_FMS 1000;2001 done:If_CharLevel 2 1')
        self.assertEqual(parsed[0].name, 'If_FMS')
        self.assertEqual(parsed[0].args, ('1000;2001',))
        self.assertEqual(parsed[0].raw, 'If_FMS 1000;2001 done')
        self.assertEqual(parsed[1].args, ('2', '1'))

    def test_accept_actions_strip_the_mc_prefix(self):
        parsed = accept_actions('MC Event_TriggerEvent 201 1 0:AcceptInventoryItem 30275 9 1')
        self.assertEqual([item.name for item in parsed],
                         ['Event_TriggerEvent', 'AcceptInventoryItem'])
        self.assertEqual(parsed[0].source, 'MC')
        self.assertEqual(parsed[0].args, ('201', '1', '0'))
        self.assertEqual(parsed[1].source, '')

    def test_rewards_and_display_items(self):
        parsed = rewards('RewardGold 1 529:RewardEudemonLevel 998 0')
        self.assertEqual([item.name for item in parsed], ['RewardGold', 'RewardEudemonLevel'])
        self.assertEqual(parsed[0].args, ('1', '529'))
        self.assertEqual(display_items('100 2 3:not a number:17 4'), [(100, 2, 3), (17, 4)])


class QuestTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = quests()

    def test_every_record_is_parsed(self):
        self.assertGreater(len(self.table), 2800)
        self.assertEqual(len({quest.id for quest in self.table.values()}), len(self.table))

    def test_starter_quest_points_at_the_authored_shield(self):
        quest = self.table[2001]
        self.assertEqual(quest.node, 610)
        self.assertEqual(quest.accept_npc, 0)
        self.assertEqual(quest.return_npc, 10204)
        self.assertEqual(quest.title, 'Lv1.來自遠方的支援')
        self.assertEqual([condition.name for condition in quest.conditions],
                         ['If_CheckWeapon', 'If_CharLevel'])
        self.assertEqual(quest.objectives[0].kind, 'equip')
        self.assertEqual(quest.objectives[0].args, (30275, 1, 1))
        self.assertEqual(quest.accept_actions[0].name, 'AcceptInventoryItem')
        self.assertEqual(quest.accept_actions[0].args, ('30275', '9', '1'))

    def test_kill_quest_keeps_all_three_targets(self):
        quest = self.table[2008]
        self.assertEqual([objective.kind for objective in quest.objectives], ['kill'] * 3)
        self.assertEqual([objective.args[0] for objective in quest.objectives],
                         [20289, 20294, 20298])
        self.assertEqual(quest.return_npc, 10330)
        self.assertEqual(quest.rewards[0].name, 'RewardEudemonLevel')

    def test_bare_npc_talk_resolves_through_the_table_reader(self):
        quest = self.table[1001]
        self.assertEqual(quest.accept_npc, 10204)
        self.assertEqual(quest.return_npc, 10205)
        self.assertEqual(quest.objectives[0].kind, 'talk')
        self.assertEqual(quest.objectives[0].args, ())

    def test_catalog_is_json_ready(self):
        catalog = quest_catalog(MISSION)
        encoded = json.dumps(catalog['2001'] if '2001' in catalog else catalog[2001])
        self.assertIn('"objectives"', encoded)
        self.assertEqual((catalog['2001'] if '2001' in catalog else catalog[2001])
                         ['objectives'][0]['kind'], 'equip')

    def test_truncated_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'S_Mission.ini')
            path.write_text('1001|mission24|title|200\n', encoding='cp950')
            with self.assertRaises(ProtocolError):
                parse_quests(path)


class SceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = Scene(SCENE)

    def test_authored_spawns_are_indexed(self):
        self.assertEqual(self.scene.positions(10204), [(220.227, 102.507)])
        self.assertEqual(len(self.scene.positions(20289)), 1)
        self.assertEqual(self.scene.named(10205)[0]['position'], (210.319, 93.5453))

    def test_event_areas_keep_their_radius(self):
        x, y, radius = self.scene.area(37)
        self.assertEqual((round(x, 3), round(y, 3), radius), (357.421, 233.48, 12.0))
        self.assertIsNone(self.scene.area(351))

    def test_gateways_point_at_their_trigger_area(self):
        gateway = self.scene.gateways[34]
        self.assertEqual((gateway['area'], gateway['event'], gateway['trigger']), (37, 401, 401))
        self.assertIn(34, self.scene.inside_gateways((357.421, 233.48, 0)[:2]))
        self.assertEqual(self.scene.inside_gateways((0, 0)), set())

    def test_dynamic_blocks_are_bitmaps(self):
        self.assertEqual(len(self.scene.blocks[44]), 15)
        self.assertTrue(self.scene.blocks[3])

    def test_invalid_block_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'S999.ini')
            path.write_text('[dynamic_block],\n1,0,10,0,10,1,0\n[globe_data],\n',
                            encoding='cp950')
            with self.assertRaises(ProtocolError):
                Scene(path)

    def test_active_obstacles_need_a_living_matching_spawn(self):
        ident = next(ident for ident in self.scene.blocks if ident in self.scene.spawns)
        spawn = self.scene.spawns[ident]
        mobs = {'m': {'template': spawn['template'], 'position': spawn['position'],
                      'alive': True}}
        self.assertEqual(self.scene.active_obstacles(mobs), set(self.scene.blocks[ident]))
        self.assertEqual(self.scene.live_barriers(mobs), {ident})
        mobs['m']['alive'] = False
        self.assertEqual(self.scene.active_obstacles(mobs), set())
        self.assertEqual(self.scene.live_barriers(mobs), set())


if __name__ == '__main__':
    unittest.main()
