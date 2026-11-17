import asyncio
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crafting import ensure,work_payload
from inventory import Inventory
from wire import ProtocolError


class CraftTests(unittest.IsolatedAsyncioTestCase):
    def test_work_packet_has_all_five_native_vectors(self):
        payload=work_payload(134,[(0,2),(1,6)])
        self.assertEqual(payload,struct.pack('<ihhH2hH2hHHH',134,1,0,2,0,1,2,2,6,0,0,0))
        with self.assertRaises(ProtocolError):work_payload(999,[(0,2),(1,6)])
        with self.assertRaises(ProtocolError):work_payload(134,[(0,2),(0,2)])

    async def test_crafting_uses_owned_materials_and_requires_real_outputs(self):
        bag=Inventory();bag.refresh=AsyncMock()
        for slot,ident in enumerate((30702,30703,30711)):bag.add(0,slot,ident)
        session=SimpleNamespace(buffers={},expect=AsyncMock(return_value=struct.pack('<Ih',0,10)))
        calls=[]
        async def send(name,payload=b''):
            calls.append((name,payload))
            if name=='PlayerWork':
                recipe=struct.unpack_from('<i',payload)[0]
                for ident in ((30702,30703) if recipe==134 else (30708,30711)):
                    bag.discard(*bag.require(ident))
                bag.add(0,7 if recipe==134 else 8,30708 if recipe==134 else 30714)
        ctx=SimpleNamespace(inventory=bag,send=send,session=session,combat=SimpleNamespace(player_id=123),report=lambda *a,**k:None)
        await ensure(ctx,30714)
        self.assertIsNotNone(bag.first(30714))
        self.assertEqual([struct.unpack_from('<i',p)[0] for n,p in calls if n=='PlayerWork'],[134,137])
        self.assertEqual([p for n,p in calls if n=='PlayerAction'],[struct.pack('<BIIIH',14,0,0,0,0)]*2)
        self.assertFalse(any('GM' in n for n,p in calls))

    async def test_missing_ingredient_does_not_send_a_crafting_request(self):
        bag=Inventory();bag.refresh=AsyncMock();bag.add(0,0,30711)
        send=AsyncMock()
        ctx=SimpleNamespace(inventory=bag,send=send)
        with self.assertRaisesRegex(ProtocolError,'owned ingredient'):
            await ensure(ctx,30714)
        send.assert_not_awaited()


if __name__=='__main__':unittest.main()
