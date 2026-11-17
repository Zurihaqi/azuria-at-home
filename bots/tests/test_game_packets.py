import sys
from pathlib import Path
import struct
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game_packets import first_inventory_item, equip_from_inventory
from wire import ProtocolError


class InventoryTests(unittest.TestCase):
    def packet(self, occupancy, size=30):
        return struct.pack('<BhhH', 1, size, 0, len(occupancy)) + occupancy + struct.pack('<I', 30275)

    def test_native_slot_zero_uses_high_bit(self):
        self.assertEqual(first_inventory_item(self.packet(b'\x80\0\0\0')), (0, 0, 30275))

    def test_slot_seven_and_eight_bit_boundaries(self):
        self.assertEqual(first_inventory_item(self.packet(b'\x01\0\0\0'))[1], 7)
        self.assertEqual(first_inventory_item(self.packet(b'\0\x80\0\0'))[1], 8)

    def test_empty_inventory_and_invalid_bitset(self):
        self.assertIsNone(first_inventory_item(self.packet(bytes(4))))
        with self.assertRaises(ProtocolError):
            first_inventory_item(self.packet(bytes(3)))

    def test_bag_and_slot_are_distinct_fields(self):
        self.assertEqual(struct.unpack('<hhhhhh', equip_from_inventory(2, 7)), (0, 7, 2, 1, -1, 0))
