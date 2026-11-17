import asyncio
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from npc import (ACTIVE, FINISHED, OFFER, READY, TURN_IN, DialogOption, DialogView,
                 Session, option_for_quest, parse_dialog, parse_mission_list,
                 parse_mission_states, parse_state_update)
from wire import ProtocolError, string


def dialog(options, ident=7, kind=1, npc=10204, tail=True):
    body = struct.pack('<ih', ident, len(options))
    for index, text, option_kind in options:
        body += struct.pack('<i', index) + string(text) + struct.pack('<h', option_kind)
    if tail:
        body += struct.pack('<bi', kind, npc)
    return body


def mission_list(ui_kind, quest, npc=10204, complete=0):
    # short Type, int MissionID, int NpcID, short CompleteNum (0x677870).
    return struct.pack('<hiih', ui_kind, quest, npc, complete)


def mission_states(pairs, extra=b''):
    return struct.pack('<h', len(pairs)) + b''.join(struct.pack('<HH', *pair) for pair in pairs) + extra


def state_update(quest, state, progress=(1, 2, 0, 0), kind=0):
    return struct.pack('<bQHhhhh', kind, quest, state, *progress)


class DialogParserTests(unittest.TestCase):
    def test_options_and_tail_are_decoded(self):
        view = parse_dialog(dialog([(0, '2001', 1), (1, '1999', 0)]))
        self.assertEqual(view.ident, 7)
        self.assertEqual(view.options[0], DialogOption(0, '2001', 1))
        self.assertEqual((view.kind, view.npc), (1, 10204))

    def test_short_capture_without_the_tail_is_accepted(self):
        view = parse_dialog(dialog([(3, '1001', 2)], tail=False))
        self.assertEqual(view.options, (DialogOption(3, '1001', 2),))
        self.assertEqual((view.kind, view.npc), (0, 0))

    def test_truncated_option_is_a_protocol_error(self):
        with self.assertRaises(ProtocolError):
            parse_dialog(struct.pack('<ih', 1, 2) + struct.pack('<i', 0))


class MissionParserTests(unittest.TestCase):
    def test_mission_list_round_trips(self):
        self.assertEqual(parse_mission_list(mission_list(OFFER, 2001)),
                         (OFFER, 2001, 10204, 0))
        self.assertEqual(len(mission_list(OFFER, 2001)), 12)
        with self.assertRaises(ProtocolError):
            parse_mission_list(mission_list(OFFER, 2001) + b'\x00')

    def test_legacy_four_int_list_is_still_accepted(self):
        payload = struct.pack('<iiii', OFFER, 2001, 10204, 1)
        self.assertEqual(parse_mission_list(payload), (OFFER, 2001, 10204, 1))

    def test_only_the_normal_state_section_is_read(self):
        payload = mission_states([(2001, ACTIVE), (1001, FINISHED)],
                                 extra=struct.pack('<hH', 1, 900) + b'trailer')
        self.assertEqual(parse_mission_states(payload), {2001: ACTIVE, 1001: FINISHED})

    def test_state_update_matches_the_verified_layout(self):
        payload = state_update(2001, READY)
        self.assertEqual(len(payload), 19)
        self.assertEqual(parse_state_update(payload), (0, 2001, READY, (1, 2, 0, 0)))
        with self.assertRaises(ProtocolError):
            parse_state_update(payload[:-1])

    def test_option_lookup_prefers_the_exact_quest_id(self):
        view = DialogView(7, (DialogOption(0, 'quest 1999', 0),
                              DialogOption(4, '2001', 1)))
        self.assertEqual(option_for_quest(view, 2001), 1)
        self.assertIsNone(option_for_quest(view, 2002))
        embedded = DialogView(7, (DialogOption(4, 'mission 2001', 1),))
        self.assertEqual(option_for_quest(embedded, 2001), 0)


class Server:
    """Fake zone that answers the dialog and mission packets in order."""

    def __init__(self, session, options, ui_kind, state):
        self.session, self.options = session, options
        self.ui_kind, self.state = ui_kind, state
        self.sent = []

    async def __call__(self, name, payload=b''):
        self.sent.append((name, payload))
        if name == 'TalkToNPC':
            actor, = struct.unpack('<I', payload)
            if actor:
                self.session.observe('DisplayDialogView', dialog(self.options,
                                                                 kind=self.ui_kind))
        elif name == 'ReplyDialog':
            position, = struct.unpack('<h', payload)
            quest = int(self.options[position][1])
            self.session.observe('EnterMissionList',
                                 mission_list(self.ui_kind, quest, complete=1))
        elif name == 'MissionListOp':
            operation, quest, value = struct.unpack('<hiH', payload)
            if operation == 9:
                self.session.observe('EnterMissionList', mission_list(OFFER, quest))
            else:
                self.session.observe('UpdateMissionState', state_update(quest, self.state))

    def names(self):
        return [name for name, _ in self.sent]


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def session(self, options=((0, '1999', 0), (1, '2001', 1)), ui_kind=OFFER,
                state=ACTIVE):
        session = Session(None)
        server = Server(session, options, ui_kind, state)
        session.send = server
        return session, server

    async def test_query_reads_the_normal_section(self):
        session, _ = self.session()
        session.observe('MissionStates', mission_states([(2001, ACTIVE)]))
        self.assertEqual(await session.query(), {2001: ACTIVE})
        self.assertEqual(session.states, {2001: ACTIVE})

    async def test_expect_consumes_matching_packets_in_order(self):
        session, _ = self.session()
        session.observe('EnterMissionList', mission_list(OFFER, 1))
        session.observe('EnterMissionList', mission_list(OFFER, 2))
        first = await session.expect('EnterMissionList',
                                     lambda raw: parse_mission_list(raw)[1] == 2)
        self.assertEqual(parse_mission_list(first)[1], 2)
        self.assertEqual(len(session.buffers['EnterMissionList']), 1)
        with self.assertRaises(ProtocolError):
            await session.expect('NeverSeen', timeout=.05)

    async def test_accept_walks_the_dialog_and_waits_for_the_state(self):
        session, server = self.session()
        state = await session.accept(10204, 2001)
        self.assertEqual(state, ACTIVE)
        self.assertEqual(server.names(), ['TalkToNPC', 'ReplyDialog', 'MissionListOp'])
        self.assertEqual(server.sent[1][1], struct.pack('<h', 1))
        self.assertEqual(server.sent[2][1], struct.pack('<hiH', 1, 2001, 65535))

    async def test_turn_in_uses_the_completion_list(self):
        session, server = self.session(ui_kind=TURN_IN, state=FINISHED)
        state = await session.turn_in(10204, 2001)
        self.assertEqual(state, FINISHED)
        self.assertEqual(server.sent[2][1], struct.pack('<hiH', 2, 2001, 65535))

    async def test_accept_from_the_virtual_board_queries_the_offer(self):
        session, server = self.session()
        state = await session.accept(0, 2001)
        self.assertEqual(state, ACTIVE)
        self.assertEqual(server.names(), ['TalkToNPC', 'MissionListOp', 'MissionListOp'])
        self.assertEqual(server.sent[0][1], struct.pack('<I', 0))
        self.assertEqual(server.sent[1][1], struct.pack('<hiH', 9, 2001, 65535))
        self.assertEqual(server.sent[2][1], struct.pack('<hiH', 1, 2001, 65535))

    async def test_accept_allows_an_immediately_ready_quest(self):
        session, _ = self.session(options=((0, '1001', 1),), state=READY)
        self.assertEqual(await session.accept(10204, 1001), READY)

    async def test_missing_quest_in_the_dialog_is_a_protocol_error(self):
        session, _ = self.session(options=((0, '1999', 0),))
        with self.assertRaises(ProtocolError):
            await session.accept(10204, 2001)

    async def test_state_update_observer_tracks_progress(self):
        session, _ = self.session()
        session.observe('UpdateMissionState', state_update(2001, READY, (1, 0, 0, 0)))
        self.assertEqual(session.states[2001], READY)
        self.assertEqual(session.progress[2001], (1, 0, 0, 0))
        self.assertEqual(await session.state(2001, READY, timeout=.1), READY)

    async def test_expected_state_without_an_update_times_out(self):
        session, _ = self.session()
        with self.assertRaises(ProtocolError):
            await session.state(2001, READY, timeout=.05)


if __name__ == '__main__':
    unittest.main()
