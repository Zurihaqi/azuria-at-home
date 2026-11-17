import sys
from pathlib import Path
import struct
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portals import route, cross


EDGE = dict(gate=2, area=4, event=100, trigger=9, target=3, region=[10, 20, 5])


class PortalTests(unittest.IsolatedAsyncioTestCase):
    def test_routing_respects_assets_public_maps_and_failed_links(self):
        graph = {'2': [EDGE], '3': [dict(event=113, target=4)]}
        self.assertEqual(route(graph, 2, 4, {2, 3, 4}, {}, now=10), [EDGE, graph['3'][0]])
        self.assertIsNone(route(graph, 2, 4, {2, 4}, {}, now=10))
        self.assertIsNone(route(graph, 2, 4, {2, 3, 4}, {(2, 100): 20}, now=10))

    async def test_gateway_check_precedes_pending_event_confirmation(self):
        node = [2]
        sent = []
        ready = AsyncMock()
        async def send(name, payload=b''):
            sent.append((name, payload))
            if name == 'TriggerNodeEvent': node[0] = 3
        with patch('portals.asyncio.sleep', new=AsyncMock()):
            self.assertTrue(await cross(EDGE, lambda: node[0], lambda: (10, 20), lambda p: p,
                                        AsyncMock(), send, ready))
        # CheckNodeExit carries the authored gateway *trigger* (9) with the
        # enter flag 0 (the handler fires condition-0 events only for 0/2);
        # flag 1 means "stepped off" and never transports.
        self.assertEqual(sent[-2:], [('CheckNodeExit', struct.pack('<hhi', 9, 0, 0)),
                                    ('TriggerNodeEvent', struct.pack('<H', 100))])
        ready.assert_awaited_once()

    async def test_automatic_gateway_transfer_does_not_send_old_map_event(self):
        node = [2]
        sent = []
        async def send(name, payload=b''):
            sent.append(name)
            if name == 'CheckNodeExit': node[0] = 3
        with patch('portals.asyncio.sleep', new=AsyncMock()):
            self.assertTrue(await cross(EDGE, lambda: node[0], lambda: (10, 20), lambda p: p,
                                        AsyncMock(), send, AsyncMock()))
        self.assertNotIn('TriggerNodeEvent', sent)

    async def test_denied_gateway_returns_failure_without_faking_a_transfer(self):
        with patch('portals.asyncio.sleep', new=AsyncMock()):
            self.assertFalse(await cross(EDGE, lambda: 2, lambda: (10, 20), lambda p: p,
                                         AsyncMock(), AsyncMock(), AsyncMock()))
