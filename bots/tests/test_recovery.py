"""Exercise actual zone death dispatch, without a server or real accounts."""
import asyncio
import json
from pathlib import Path
import re
import socket
import struct
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import probe_login as probe
from reporting import Reporter
from wire import ProtocolError, string


def protocol_map():
    names = set()
    root = Path(probe.__file__).parent
    for name in ('probe_login.py', 'combat.py'):
        names.update(re.findall(r"['\"]((?:CNC|CNE)_[A-Za-z0-9_]+)['\"]", (root / name).read_text()))
    for prefix in ('CNC_CZ_Client', 'CNE_CZ_ZoneServer'):
        for suffix in ('EnterNodePlayerData', 'EnterNodeEquipAndSpell', 'EnterNodeInventory',
                       'EnterNodeShortcut', 'EnterNodeElfInfo', 'EnterNodeCoinsData'):
            names.add(prefix + suffix)
    return {name: index for index, name in enumerate(sorted(names), 1)}


class NativeSession:
    def __init__(self, protocol, packets, cycles=1):
        self.protocol, self.packets = protocol, asyncio.Queue()
        for packet in packets:
            self.packets.put_nowait(packet)
        self.sent, self.closed, self.cycles = [], False, cycles
        self.revives = 0

    async def handshake(self):
        return 1024

    async def receive(self):
        packet = await self.packets.get()
        if isinstance(packet, Exception):
            raise packet
        return packet

    async def send(self, command, payload=b''):
        self.sent.append((command, payload))
        if command == self.protocol['CNE_CZ_ZoneServerRevive']:
            self.revives += 1
            self.packets.put_nowait((self.protocol['CNC_CZ_ClientRevive'], struct.pack('<I', 77)))
            if self.revives < self.cycles:
                self.packets.put_nowait((self.protocol['CNC_CZ_ClientDie'], struct.pack('<IIBH', 77, 10, 0, 1)))
            else:
                self.packets.put_nowait(ProtocolError('Fixture complete'))

    async def close(self):
        self.closed = True


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_world_keepalive_matches_native_field_layout(self):
        from wire import Reader
        data = Reader(probe.world_keepalive_payload())
        self.assertEqual([data.text() for _ in range(8)], [''] * 8)
        self.assertEqual(data.number('i'), 0)
        self.assertEqual([data.text() for _ in range(2)], ['', ''])
        self.assertEqual(data.number('h'), 0)
        data.end()

    async def test_silent_earlier_service_does_not_stop_keepalives(self):
        class SilentConnection:
            def __init__(self):
                self.sent = []
                self.three_sends = asyncio.Event()
                self.receiving = False
            async def send(self, command, payload):
                self.sent.append((command, payload))
                if len(self.sent) >= 3:
                    self.three_sends.set()
            async def receive(self):
                self.receiving = True
                try:
                    await asyncio.Event().wait()
                finally:
                    self.receiving = False
        connection = SilentConnection()
        task = asyncio.create_task(probe.keep_session_alive(connection, 9, string(''), interval=.01))
        try:
            await asyncio.wait_for(connection.three_sends.wait(), 1)
            self.assertTrue(connection.receiving)
            self.assertEqual(connection.sent[:3], [(9, b'\0\0')] * 3)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertFalse(connection.receiving)

    async def session(self, *, hp=10, deaths=(77,), cycles=1, ping=False):
        protocol = protocol_map()
        def packet(name, payload):
            return protocol['CNC_CZ_Client' + name], payload
        packets = [
            packet('EnterNodeNodeData', struct.pack('<hhbfffIHHh', 2, 0, 0, 500., 350., 0., 0, 0, 0, 0)),
            packet('EnterNodePlayerData', struct.pack('<I', 77) + string('Awan') + string('') * 3 +
                   struct.pack('<fB', 8.6, 0) + bytes(4) + struct.pack('<Hii', 3, hp, 400)),
        ]
        if hp == 0:
            packets.extend(packet(name, b'\0' if name == 'EnterNodeInventory' else b'') for name in
                           ('EnterNodeEquipAndSpell', 'EnterNodeInventory', 'EnterNodeShortcut',
                            'EnterNodeElfInfo', 'EnterNodeCoinsData'))
        packets.extend(packet('Die', struct.pack('<IIBH', who, 10, 0, 1)) for who in deaths)
        if ping:
            packets.append(packet('Hello', b''))
        if hp > 0 and 77 not in deaths:
            packets.append(ProtocolError('Fixture complete'))
        native = NativeSession(protocol, packets, cycles)
        ticket = bytes(8) + socket.inet_aton(probe.server_ip()) + struct.pack('<H', 10020)
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            (state / 'zone-protocol.json').write_text(json.dumps(protocol))
            reporter = Reporter(state, 'normal')
            with patch.object(probe, 'STATE', state), patch.object(probe, 'NORMAL_WORLD', False), \
                 patch.object(probe, 'REPORTER', reporter), patch.object(probe, 'Connection', return_value=native), \
                 patch.object(probe, 'report'), patch.object(sys, 'argv', ['test', '--continuous']), \
                 patch.object(probe.asyncio, 'open_connection', AsyncMock(return_value=(None, None))):
                with self.assertRaisesRegex(ProtocolError, 'Fixture complete'):
                    await asyncio.wait_for(probe.zone_session(ticket), 12)
            events = [json.loads(line) for line in (state / 'events-public.jsonl').read_text().splitlines()]
            final = json.loads((state / 'status-public.json').read_text())
        self.assertTrue(native.closed)
        self.assertFalse(any(command == protocol['CNE_CZ_ZoneServerSafeQuitReq'] for command, _ in native.sent))
        return native, events, final

    async def test_own_death_sends_one_revive_even_with_duplicate_notice(self):
        native, events, _ = await self.session(deaths=(77, 77))
        self.assertEqual(native.revives, 1)
        self.assertIn((native.protocol['CNE_CZ_ZoneServerRevive'], struct.pack('<i', 1)), native.sent)
        self.assertTrue(any('respawn confirmed' in event['message'] for event in events))

    async def test_other_character_death_does_not_revive_or_logout(self):
        native, _, _ = await self.session(deaths=(88,))
        self.assertEqual(native.revives, 0)

    async def test_login_at_zero_hp_requests_native_respawn_after_map_load(self):
        native, _, _ = await self.session(hp=0, deaths=())
        self.assertEqual(native.revives, 1)

    async def test_repeated_deaths_pause_combat_but_keep_respawning(self):
        native, _, final = await self.session(cycles=4)
        self.assertEqual(native.revives, 4)
        self.assertEqual(final['phase'], 'paused')
        self.assertIn('repeated deaths', final['task'])

    async def test_server_liveness_challenge_is_acknowledged_immediately(self):
        native, _, _ = await self.session(deaths=(), ping=True)
        echoes = [(command, payload) for command, payload in native.sent
                  if command == native.protocol['CNE_CZ_ZoneServerEcho']]
        self.assertEqual(echoes, [(native.protocol['CNE_CZ_ZoneServerEcho'], b'')])


if __name__ == '__main__':
    unittest.main()
