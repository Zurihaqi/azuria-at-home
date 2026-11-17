from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inventory import Inventory
from wire import ProtocolError


def clone(ident=30301, quantity=1):
    return struct.pack('<IhhHB', ident, quantity, 100, 0, 8) + bytes(7)


def snapshot(quantity=4):
    return struct.pack('<BhhHB', 1, 8, 0, 1, 0x20) + clone(quantity=quantity)


class InventoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_stack_after_login_and_incremental_update(self):
        bag = Inventory()
        bag.observe('EnterNodeInventory', snapshot())
        self.assertEqual(bag.stack_count(30301), 4)
        self.assertEqual(bag.first(30301), (0, 2))
        bag.observe('ModifyItemDurability', struct.pack('<hhhhh', 0, 2, 5, 100, 0))
        self.assertEqual(bag.stack_count(30301), 5)
        # An equipment durability change must not change inventory slot 2.
        bag.observe('ModifyItemDurability', struct.pack('<hhhhh', 1, 2, 30, 100, 0))
        self.assertEqual(bag.stack_count(30301), 5)

    async def test_new_stacks_sum_and_removed_or_replaced_slots_lose_counts(self):
        bag = Inventory()
        for slot, quantity in ((2, 3), (3, 2)):
            bag.observe('PutItemIntoInventory', struct.pack('<hh', 0, slot) + clone(quantity=quantity))
        self.assertEqual(bag.stack_count(30301), 5)
        bag.observe('PutItemIntoInventory', struct.pack('<hhI', 0, 2, 0))
        self.assertEqual(bag.stack_count(30301), 2)
        bag.observe('PutItemIntoInventory', struct.pack('<hhI', 0, 3, 30635))
        self.assertEqual(bag.stack_count(30301), 0)
        self.assertEqual(bag.stack_count(30635), 0)  # Prefix gives no quantity.

    async def test_refresh_requires_new_native_snapshot_and_replaces_old_slots(self):
        bag = Inventory()
        bag.observe('EnterNodeInventory', snapshot(1))
        async def send(name, payload):
            self.assertEqual((name, payload), ('EnterNodeInventory', b''))
            bag.observe('EnterNodeInventory', snapshot(4))
        await bag.refresh(send)
        self.assertEqual(bag.stack_count(30301), 4)
        bag.observe('EnterNodeInventory', b'\0')
        self.assertEqual(bag.stack_count(30301), 0)

    async def test_stale_snapshot_cannot_satisfy_refresh(self):
        bag = Inventory()
        bag.observe('EnterNodeInventory', snapshot())
        async def send(*args):
            pass
        with self.assertRaisesRegex(ProtocolError, 'snapshot timed out'):
            await bag.refresh(send, timeout=0)


if __name__ == '__main__':
    unittest.main()
