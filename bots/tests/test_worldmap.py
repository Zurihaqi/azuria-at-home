import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content import Objective
from worldmap import build_index, choose, load, locations, objective_template, write_index


def step(kind, args, command=None):
    return Objective(kind, tuple(args), command or kind)


class ObjectiveTemplateTests(unittest.TestCase):
    def test_actor_kinds_use_their_template(self):
        from types import SimpleNamespace
        quest = SimpleNamespace(accept_npc=10, return_npc=11)
        self.assertEqual(objective_template(step('kill', (41165, 1)), quest), 41165)
        self.assertEqual(objective_template(step('collect_drop', (41165, 100, 30635, 1)), quest), 41165)
        self.assertEqual(objective_template(step('talk', (40334,)), quest), 40334)
        self.assertEqual(objective_template(step('deliver', (40335, 2, 0, 1)), quest), 40335)

    def test_map_local_steps_are_not_travelled_for(self):
        from types import SimpleNamespace
        quest = SimpleNamespace(accept_npc=10, return_npc=11)
        self.assertIsNone(objective_template(step('travel', (21,)), quest))
        self.assertIsNone(objective_template(step('collect', (30301,)), quest))
        self.assertIsNone(objective_template(step('kill', ()), quest))
        # UseTimes is the 1014 potion: an item action, not an NPC visit.
        self.assertIsNone(objective_template(step('use_item', (1,), 'UseTimes'), quest))
        self.assertEqual(objective_template(step('use_item', (), 'NPCItem'), quest), 11)


class IndexTests(unittest.TestCase):
    def scene(self, node, rows, blocks=''):
        text = ('[globe_data],\nS%03d.nif,192,192,V5,S%03d.smp,\n[biology],\n' % (node, node)
                + ''.join(row + '\n' for row in rows) + blocks)
        return text

    def test_build_and_round_trip_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            maps = Path(tmp)
            (maps / 'S002.ini').write_text(self.scene(2, [
                '1,40334,1,1,0,10.5,20.25,0,0',
                '2,41165,1,1,0,21.5722,88.1021,0,0']), encoding='cp950')
            (maps / 'S622.ini').write_text(self.scene(622, [
                '1,41165,1,1,0,21.5722,88.1021,0,0']), encoding='cp950')
            (maps / 'S_Mission.ini').write_text('not a scene', encoding='cp950')
            index = write_index(maps)
            self.assertEqual(set(locations(index, 41165)), {'2', '622'})
            self.assertEqual(locations(index, 40334), {'2': [[10.5, 20.25]]})
            loaded = load(maps / 'world-index.json')
            self.assertEqual(locations(loaded, 41165),
                             {'2': [(21.572, 88.102)], '622': [(21.572, 88.102)]})

    def test_choose_prefers_the_current_map(self):
        index = dict(templates={'9': {'2': [(1, 1)], '3': [(2, 2)]}})
        self.assertEqual(choose(index, 9, 2, {}, {2, 3}, {}), (2, []))
        self.assertIsNone(choose(index, 99, 2, {}, {2}, {}))

    def test_choose_routes_to_the_nearest_reachable_map(self):
        index = dict(templates={'9': {'4': [(1, 1)], '5': [(2, 2)]}})
        graph = {'2': [dict(target=3, event=1)],
                 '3': [dict(target=4, event=2), dict(target=5, event=3)]}
        node, route = choose(index, 9, 2, graph, {2, 3, 4, 5}, {})
        self.assertEqual((node, len(route)), (4, 2))
        self.assertEqual([edge['target'] for edge in route], [3, 4])

    def test_choose_ignores_unpackaged_and_blocked_maps(self):
        index = dict(templates={'9': {'4': [(1, 1)], '5': [(2, 2)]}})
        graph = {'2': [dict(target=4, event=1), dict(target=5, event=2)]}
        self.assertIsNone(choose(index, 9, 2, graph, {2}, {}))
        self.assertIsNone(choose(index, 9, 2, graph, {2, 4}, {(2, 1): 99}, now=10))
        self.assertEqual(choose(index, 9, 2, graph, {2, 4}, {(2, 1): 9}, now=10)[0], 4)


if __name__ == '__main__':
    unittest.main()
