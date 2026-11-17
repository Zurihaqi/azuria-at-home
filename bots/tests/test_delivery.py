import struct
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content import Objective
from npc import Session, DialogView, DialogOption
from objectives import drive_deliver
from wire import string, ProtocolError


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_reads_native_personal_progress(self):
        session = Session(AsyncMock())
        key = (1005 << 32) | (4 << 16) | 10209
        payload = struct.pack('<hhhQH', 0, 0, 1, key, 1)
        session.observe('MissionStates', payload)
        self.assertEqual(session.personal[key], 1)
        session.observe('UpdateMissionState', struct.pack('<bQHhhhh', 1, key, 2, 0, 0, 0, 0))
        self.assertEqual(session.personal[key], 2)

    async def test_new_talk_cannot_consume_previous_npc_dialog(self):
        async def send(name, payload):
            session.observe('DisplayDialogView', struct.pack('<ihbi', 10057, 0, -1, 10211))
        session = Session(send)
        session.observe('DisplayDialogView', struct.pack('<ihbi', 10055, 0, -1, 10209))
        self.assertEqual((await session.talk(999)).ident, 10057)

    def context(self, session):
        return SimpleNamespace(quest=SimpleNamespace(id=1005), session=session,
            scene=SimpleNamespace(positions=lambda template: [(1, 1)]),
            talk_to=AsyncMock(return_value=55))

    async def test_completed_delivery_is_not_repeated(self):
        key = (1005 << 32) | (4 << 16) | 10209
        session = SimpleNamespace(personal={key: 1})
        ctx = self.context(session)
        await drive_deliver(ctx, Objective('deliver', (10209,10055,30294,1), 'ItemGiven'))
        ctx.talk_to.assert_not_awaited()

    async def test_delivery_selects_quest_entry_and_requires_server_confirmation(self):
        key = (1005 << 32) | (4 << 16) | 10209
        session = SimpleNamespace(personal={}, states={},
            talk=AsyncMock(return_value=DialogView(5153, (DialogOption(-3,'1005',0),))),
            choose=AsyncMock())
        async def expect(name, predicate, timeout):
            payload = struct.pack('<ihbi', 10055, 0, -1, 10209)
            self.assertTrue(predicate(payload))
            session.personal[key] = 1
            return payload
        session.expect = expect
        await drive_deliver(self.context(session), Objective('deliver', (10209,10055,30294,1), 'ItemGiven'))
        self.assertEqual(session.choose.await_args.args[1], 0)

    async def test_unknown_delivery_option_stops_without_selecting(self):
        session = SimpleNamespace(personal={}, talk=AsyncMock(return_value=DialogView(5, ())), choose=AsyncMock())
        with self.assertRaises(ProtocolError):
            await drive_deliver(self.context(session), Objective('deliver', (10209,10055,30294,1), 'ItemGiven'))
        session.choose.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
