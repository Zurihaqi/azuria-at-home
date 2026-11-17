import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content import Quest, Objective
from npc import ACTIVE, FINISHED, READY
from quest_engine import Engine, Journal, compile_quest, failure_kind, progress
from wire import ProtocolError


def quest(ident=100, kind='kill', command='MonsterKilled', args=(40001, 1)):
    return Quest(ident, 'test', 'Test', 2, 0, 'main', 10, 11, (), (),
                 (Objective(kind, args, command),), (), ())


def context(q, state=ACTIVE):
    session = SimpleNamespace(states={q.id: state} if state is not None else {}, progress={}, personal={})
    async def accept(actor, ident, timeout): session.states[ident] = ACTIVE
    async def turn_in(actor, ident, timeout): session.states[ident] = FINISHED
    async def require(ident, expected, timeout):
        if session.states.get(ident) != expected:
            raise ProtocolError('Native server did not mark quest ready')
    session.accept, session.turn_in, session.state = AsyncMock(side_effect=accept), AsyncMock(side_effect=turn_in), require
    return SimpleNamespace(session=session, quest=None, talk_to=AsyncMock(return_value=99))


class CompilerTests(unittest.TestCase):
    def test_unknown_and_malformed_commands_are_explicit_blockers(self):
        self.assertFalse(compile_quest(quest(kind='craft', command='Craft')).executable)
        self.assertFalse(compile_quest(quest(args=())).executable)
        self.assertFalse(compile_quest(quest(kind='collect', command='ItemGot', args=(1,))).executable)

    def test_hammer_semantics_are_preserved(self):
        q = quest(1010, args=(40338, 2, 0))
        self.assertEqual(compile_quest(q).steps[0].driver, 'wake_workers')
        self.assertFalse(compile_quest(replace(q, id=9999)).executable)

    def test_potion_semantics_select_an_action_instead_of_passive_waiting(self):
        q = quest(1014, kind='buff', command='CheckBuff', args=(1, 45134, 1))
        self.assertEqual(compile_quest(q).steps[0].driver, 'drink_quest_potion')

    def test_progress_ignores_other_quests(self):
        ctx = context(quest())
        before = progress(ctx.session, 100)
        ctx.session.states[999] = READY
        ctx.session.personal[(999 << 32) | 1] = 5
        self.assertEqual(progress(ctx.session, 100), before)


class JournalTests(unittest.TestCase):
    def test_fixed_driver_gets_fresh_retry_budget_without_changing_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'attempts.json'
            first = Journal(path, lambda:1000, driver_revision='old')
            first.failed(1017, 'objective', ProtocolError('No progress'))
            self.assertFalse(Journal(path, lambda:1001, driver_revision='old').allowed(1017))
            revised = Journal(path, lambda:1001, driver_revision='fixed')
            self.assertTrue(revised.allowed(1017))
            self.assertTrue(any(e['outcome']=='failed' for e in revised.events))

    def test_backoff_persists_without_modifying_progress(self):
        now = [1000]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'attempts.json'
            journal = Journal(path, lambda: now[0])
            self.assertEqual(journal.failed(100, 'objective:0', ProtocolError('MoveSelf failed')), 60)
            self.assertFalse(Journal(path, lambda: now[0]).allowed(100))
            now[0] += 61
            self.assertTrue(Journal(path, lambda: now[0]).allowed(100))
            self.assertEqual(journal.failed(100, 'objective:0', ProtocolError('MoveSelf failed')), 120)
            self.assertEqual(journal.failures['100']['kind'], 'navigation')
            self.assertNotIn('states', json.loads(path.read_text()))


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_accept_ready_and_finish_all_required(self):
        q = quest()
        ctx = context(q, state=None)
        async def kill(ctx, step): ctx.session.states[q.id] = READY
        engine = Engine({q.id: q}, Journal(), drivers={'kill': kill})
        close, recover = AsyncMock(), AsyncMock()
        self.assertTrue(await engine.execute(q, ctx, ctx.talk_to, close, recover))
        ctx.session.accept.assert_awaited_once()
        ctx.session.turn_in.assert_awaited_once()
        recover.assert_not_awaited()
        self.assertEqual(ctx.session.states[q.id], FINISHED)

    async def test_noop_driver_is_not_completion(self):
        q = quest()
        ctx = context(q)
        driver = AsyncMock()
        engine = Engine({q.id: q}, Journal(), drivers={'kill': driver})
        recover = AsyncMock()
        self.assertFalse(await engine.execute(q, ctx, ctx.talk_to, AsyncMock(), recover))
        ctx.session.turn_in.assert_not_awaited()
        recover.assert_awaited_once_with('no_progress')
        self.assertEqual(ctx.session.states[q.id], ACTIVE)
        self.assertFalse(engine.journal.allowed(q.id))

    async def test_cancel_for_party_or_shutdown_does_not_consume_retry(self):
        q = quest()
        ctx = context(q)
        async def interrupted(*args): raise asyncio.CancelledError()
        engine = Engine({q.id: q}, Journal(), drivers={'kill': interrupted})
        with self.assertRaises(asyncio.CancelledError):
            await engine.execute(q, ctx, ctx.talk_to, AsyncMock(), AsyncMock())
        self.assertTrue(engine.journal.allowed(q.id))
        self.assertEqual(engine.journal.events[-1]['outcome'], 'interrupted')

    async def test_native_death_charges_the_retry_budget(self):
        q = quest()
        ctx = context(q)
        ctx.combat = SimpleNamespace(last_death=(41165, __import__('time').monotonic() - 2))
        async def interrupted(*args): raise asyncio.CancelledError()
        engine = Engine({q.id: q}, Journal(), drivers={'kill': interrupted})
        with self.assertRaises(asyncio.CancelledError):
            await engine.execute(q, ctx, ctx.talk_to, AsyncMock(), AsyncMock())
        self.assertFalse(engine.journal.allowed(q.id))
        self.assertEqual(engine.journal.failures['100']['kind'], 'combat_loss')
        self.assertEqual(engine.journal.events[-1]['outcome'], 'failed')
        self.assertIsNone(ctx.combat.last_death)

    async def test_stale_death_persona_yields_to_a_plain_interrupt(self):
        q = quest()
        ctx = context(q)
        import time as time_module
        ctx.combat = SimpleNamespace(last_death=(41165, time_module.monotonic() - 120))
        async def interrupted(*args): raise asyncio.CancelledError()
        engine = Engine({q.id: q}, Journal(), drivers={'kill': interrupted})
        with self.assertRaises(asyncio.CancelledError):
            await engine.execute(q, ctx, ctx.talk_to, AsyncMock(), AsyncMock())
        self.assertTrue(engine.journal.allowed(q.id))
        self.assertEqual(engine.journal.events[-1]['outcome'], 'interrupted')

    def test_failure_kind_detects_combat_losses(self):
        self.assertEqual(failure_kind(ProtocolError('character died to biology 41165')), 'combat_loss')

    async def test_finished_quest_never_offered_and_failed_quest_yields_to_next(self):
        first, second = quest(100), quest(101)
        ctx = context(first)
        engine = Engine({100: first, 101: second}, Journal())
        engine.journal.failed(100, 'accept', ProtocolError('Quest not in the NPC dialog'))
        self.assertEqual([q.id for q in engine.candidates(ctx.session, 10, 1, {10}, 2)], [101])
        ctx.session.states[101] = FINISHED
        self.assertEqual(engine.candidates(ctx.session, 10, 1, {10}, 2), [])

    async def test_ready_unsupported_quest_can_be_turned_in(self):
        q = quest(kind='craft', command='Craft')
        ctx = context(q, READY)
        engine = Engine({q.id: q}, Journal())
        self.assertEqual(engine.candidates(ctx.session, 10, 1, {10}, 2), [q])
        self.assertTrue(await engine.execute(q, ctx, ctx.talk_to, AsyncMock(), AsyncMock()))

    async def test_map_aware_engine_travels_before_touching_a_distant_actor(self):
        q = quest(args=(41165, 1))
        ctx = context(q)
        node = [2]
        travelled = []

        def locate(template):
            return 622 if template == 41165 else 2

        async def travel(target):
            travelled.append(target)
            node[0] = target

        async def kill(ctx, step):
            self.assertEqual(node[0], 622)
            ctx.session.states[q.id] = READY

        engine = Engine({q.id: q}, Journal(), drivers={'kill': kill},
                        locate=locate, travel=travel)
        engine.locate = locate
        self.assertTrue(await engine.execute(q, ctx, ctx.talk_to, AsyncMock(), AsyncMock(),
                                             get_node=lambda: node[0]))
        self.assertEqual(travelled, [622, 2])
        self.assertEqual(node[0], 2)


if __name__ == '__main__': unittest.main()
