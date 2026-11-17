"""Synthetic, temporary fixtures only. These never become live training data."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from encounter_learning import (Features, Store, Tracker, clean, load_model,
                                predict, rank, train, save_model)

PROTOCOL = {'CNC_CZ_ClientMeleeAttack':1, 'CNC_CZ_ClientDie':2,
            'CNC_CZ_ClientCantSee':3, 'CNC_CZ_ClientSpellCast':4,
            'CNC_CZ_ClientSpellHitToLife':5}
ACTOR, TARGET = 50000002, 900


class EncounterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name)/'encounters.sqlite3')
        self.addCleanup(self.store.close)
        self.now = [0.]
        self.tracker = Tracker(self.store, PROTOCOL, clock=lambda:self.now[0])
        self.tracker.map_id, self.tracker.level, self.tracker.capability = 2, 6, 'ordinary-gear:melee'

    def begin(self):
        self.tracker.begin(ACTOR, TARGET, 40323)
        self.now[0] += 10

    def damage(self, attacker, victim, damage=10):
        self.tracker.observe(1, struct.pack('<IIihh', attacker,victim,damage,0,0))

    def death(self, victim, killer):
        self.tracker.observe(2, struct.pack('<IIBH',victim,killer,0,1))

    def test_native_solo_kill_records_once_with_damage(self):
        self.begin()
        self.damage(ACTOR,TARGET,100)
        self.damage(TARGET,ACTOR,20)
        self.death(TARGET,ACTOR)
        self.tracker.finish('interrupted')
        rows = self.store.rows()
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['outcome'], rows[0]['damage_out'],rows[0]['damage_in']), ('kill',100,20))
        self.assertEqual(rows[0]['seconds'],10)
        self.assertIsNone(rows[0]['xp_gain'])
        self.assertEqual(len(clean(rows)),1)

    def test_own_death_is_recorded_before_gameplay_cancellation(self):
        self.begin()
        self.death(ACTOR,TARGET)
        self.tracker.finish('interrupted')
        self.assertEqual([r['outcome'] for r in self.store.rows()], ['death'])

    def test_disconnect_timeout_and_lost_target_are_not_deaths(self):
        for result in ('disconnect','timeout','interrupted'):
            self.begin()
            self.tracker.finish(result)
        self.begin()
        self.tracker.observe(3,struct.pack('<I',TARGET))
        self.assertEqual(len(self.store.rows()),4)
        self.assertEqual(clean(self.store.rows()),[])

    def test_assisted_and_multi_enemy_fights_are_excluded(self):
        self.begin()
        self.damage(42,TARGET)
        self.death(TARGET,ACTOR)
        self.begin()
        self.death(TARGET,42)
        self.begin()
        self.damage(43,ACTOR)
        self.death(ACTOR,TARGET)
        self.assertEqual(clean(self.store.rows()),[])

    def test_unparsed_magic_cannot_teach_a_falsely_fast_solo_kill(self):
        self.begin()
        self.tracker.observe(5, b'not decoded')
        self.death(TARGET,ACTOR)
        self.assertEqual(clean(self.store.rows()),[])

    def spell(self, caster, victim):
        self.tracker.observe(5, struct.pack('<HIIiiiBB', 51401,caster,victim,10,0,0,0,0))

    def test_unrelated_nearby_magic_is_not_assistance(self):
        self.begin()
        self.spell(42,43)
        self.death(TARGET,ACTOR)
        self.assertEqual(len(clean(self.store.rows())),1)

    def test_enemy_skill_is_part_of_the_same_duel(self):
        self.begin()
        self.spell(TARGET,ACTOR)
        self.death(TARGET,ACTOR)
        self.assertEqual(len(clean(self.store.rows())),1)

    def test_external_spell_damage_and_healing_are_excluded_with_reasons(self):
        for victim in (TARGET,ACTOR):
            self.begin()
            self.spell(42,victim)
            self.death(TARGET,ACTOR)
        self.assertEqual(clean(self.store.rows()),[])
        self.assertEqual({r['exclusion'] for r in self.store.rows()},{'external_spell'})

    def test_boosted_human_and_unknown_monsters_are_not_recorded(self):
        self.tracker.begin(50000001,TARGET,40323)
        self.death(TARGET,50000001)
        self.tracker.begin(ACTOR,TARGET,40338)
        self.death(TARGET,ACTOR)
        self.assertEqual(self.store.rows(),[])

    def test_missing_or_unverified_state_abstains(self):
        self.tracker.capability = None
        self.begin()
        self.death(TARGET,ACTOR)
        self.assertEqual(self.store.rows(),[])

    def test_storage_failure_does_not_raise_into_gameplay(self):
        self.begin()
        self.store.db.execute('PRAGMA query_only=ON')
        self.death(TARGET,ACTOR)
        self.assertFalse(self.tracker.enabled)

    def fixture(self):
        for session, size in (('first',40),('second',40),('holdout',20)):
            for index in range(size):
                rabbit = index % 2 == 0
                enemy = 40323 if rabbit else 40325
                won = rabbit or (index//2) % 4 == 0
                self.store.record(ident=f'{session}-{index}',session=session,actor=ACTOR,
                    started=index,features=Features(2,6,enemy,3 if rabbit else 5,'ordinary-gear:melee'),
                    outcome='kill' if won else 'death',seconds=30 if rabbit else 10)
        return self.store.rows()

    def test_training_uses_whole_session_holdout_and_rejects_deadly_fast_target(self):
        model = train(self.fixture())
        self.assertTrue(model['approved'],model)
        self.assertEqual((model['training_rows'],model['holdout_rows']), (80,20))
        self.assertLess(model['metrics']['brier'],model['metrics']['baseline_brier'])
        ranked = rank(model,map_id=2,level=6,capability='ordinary-gear:melee',candidates=[40323,40325])
        self.assertEqual([r['enemy'] for r in ranked],[40323])
        self.assertAlmostEqual(ranked[0]['seconds'],30)

    def test_out_of_distribution_gear_levels_and_enemy_types_abstain(self):
        model = train(self.fixture())
        for f in (Features(2,6,40323,3,'different-gear'),Features(2,40,40323,3,'ordinary-gear:melee'),
                  Features(2,6,40338,3,'ordinary-gear:melee'),Features(610,6,40323,3,'ordinary-gear:melee')):
            self.assertIsNone(predict(model['examples'],f))

    def test_cold_start_and_insufficient_sessions_do_not_activate(self):
        self.assertFalse(train([])['approved'])
        rows = self.fixture()
        for row in rows:
            row['session'] = 'only-one'
        self.assertFalse(train(rows)['approved'])

    def test_changed_holdout_outcomes_block_a_bad_model(self):
        rows = self.fixture()
        for row in rows:
            if row['session']=='holdout':
                row['outcome'] = 'death' if row['enemy']==40323 else 'kill'
        self.assertFalse(train(rows)['approved'])

    def test_model_loader_rejects_unapproved_malformed_and_nonfinite_files(self):
        path = Path(self.folder.name)/'model.json'
        model = train(self.fixture())
        path.write_text(json.dumps(model))
        self.assertIsNotNone(load_model(path))
        model['approved'] = False
        path.write_text(json.dumps(model))
        self.assertIsNone(load_model(path))
        self.assertEqual(rank(model,map_id=2,level=6,capability='ordinary-gear:melee',candidates=[40323]),[])
        model['approved'] = True
        model['examples'][0]['seconds'] = float('nan')
        path.write_text(json.dumps(model))
        self.assertIsNone(load_model(path))
        path.write_text('{broken')
        self.assertIsNone(load_model(path))

    def test_model_is_published_atomically_without_promoting_unapproved_data(self):
        path = Path(self.folder.name)/'model.json'
        model = train(self.fixture())
        save_model(model,path)
        self.assertIsNotNone(load_model(path))
        save_model(train([]),path)
        self.assertIsNone(load_model(path))
        self.assertEqual(list(path.parent.glob('*.tmp-*')), [])


if __name__=='__main__':
    unittest.main()
