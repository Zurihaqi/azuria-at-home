import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from potential import (PAGE_ATTACK, PAGE_DEFENSE, build_allocation, decode_update, Allocator)
from wire import ProtocolError


def snapshot(page=0, s1=0, s2=0, s3=0, free=7):
    return struct.pack('<BHHHh', page, s1, s2, s3, free)


class DecodeTests(unittest.TestCase):
    def test_decode_native_nine_byte_update(self):
        view = decode_update(snapshot(page=1, s1=12, s2=3, s3=44, free=9))
        self.assertEqual(view, dict(page=PAGE_DEFENSE, slots=(12, 3, 44), free=9))

    def test_decode_rejects_foreign_payloads(self):
        self.assertIsNone(decode_update(b''))
        self.assertIsNone(decode_update(bytes(8)))
        self.assertIsNone(decode_update(bytes(10)))

    def test_decode_rejects_unknown_page_or_cap_violations(self):
        self.assertIsNone(decode_update(snapshot(page=2)))
        self.assertIsNone(decode_update(snapshot(s1=100)))
        self.assertIsNone(decode_update(snapshot(s3=120)))

    def test_decode_keeps_free_budget_even_when_negative(self):
        view = decode_update(snapshot(free=-3))
        self.assertEqual(view['free'], -3)


class AllocationTests(unittest.TestCase):
    def test_both_page_budgets_spent_once_then_native_confirmation_required(self):
        allocator = Allocator()
        for page in (0, 1):
            view = decode_update(snapshot(page=page, free=3))
            self.assertFalse(allocator.observe(view))
            self.assertEqual(allocator.request(view), (3, 0, 0))
            self.assertIsNone(allocator.request(view))
            self.assertFalse(allocator.observe(view))
            self.assertTrue(allocator.observe(decode_update(snapshot(page=page, s1=3, free=0))))
            self.assertFalse(allocator.summary()[str(page)]['awaiting_confirmation'])

    def test_allocations_obey_slot_caps_and_never_invent_free_points(self):
        allocator = Allocator()
        view = decode_update(snapshot(page=1, s1=98, free=3))
        self.assertEqual(allocator.request(view), (1, 2, 0))
        self.assertIsNone(Allocator().request(decode_update(snapshot(free=0))))
    def test_attack_page_mode_byte_zero(self):
        self.assertEqual(build_allocation(PAGE_ATTACK, (5, 0, 0)), bytes([0, 5, 0, 0]))

    def test_defense_page_allocates_all_three_slots(self):
        self.assertEqual(build_allocation(PAGE_DEFENSE, (1, 2, 3)), bytes([1, 1, 2, 3]))

    def test_empty_or_invalid_allocations_are_rejected(self):
        with self.assertRaises(ProtocolError): build_allocation(PAGE_ATTACK, (0, 0, 0))
        with self.assertRaises(ProtocolError): build_allocation(PAGE_ATTACK, (-1, 0, 0))
        with self.assertRaises(ProtocolError): build_allocation(PAGE_ATTACK, (100, 0, 0))
        with self.assertRaises(ProtocolError): build_allocation(7, (1, 0, 0))
        with self.assertRaises(ProtocolError): build_allocation(PAGE_ATTACK, (1, 0))


if __name__ == '__main__':
    unittest.main()
