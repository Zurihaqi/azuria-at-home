import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from movement import (DIRECTIONS, MAX_STEPS, Segment, Sync, blob_cell, blob_point,
                      chunks, decode_blob, decode_move, encode_blob, path_cells,
                      plan, replica_accept, server_blocked, wire_speed)
from navigation import Grid
from wire import ProtocolError
from movement import wire_heading

ROOT = Path(__file__).resolve().parents[2]
MAPS = [ROOT / 'staging/ultimate/hxsy/Data/NodeMap/S610.smp',
        Path('/opt/ak-bot-prototype/maps/S610.smp')]


def grid(cells, width=2, height=2):
    return Grid(0, 0, width, height, bytes(cells))


class CellTests(unittest.TestCase):
    def test_facing_matches_native_axis_convention(self):
        self.assertEqual(wire_heading(1, 0), 4712)
        self.assertEqual(wire_heading(0, 1), 3142)
        self.assertEqual(wire_heading(-1, 0), 1571)
        self.assertEqual(wire_heading(0, -1), 0)
        with self.assertRaises(ProtocolError): wire_heading(0, 0)

    def test_heading_segments_split_at_turns_without_losing_steps(self):
        cells = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
        parts = chunks(cells, split_turns=True)
        self.assertEqual(parts, [tuple(cells[:3]), tuple(cells[2:])])
    def test_cell_centre_matches_the_observed_reset_coordinate(self):
        self.assertEqual(blob_point(419, 0)[0], 209.75)

    def test_world_cell_round_trips_through_the_centre(self):
        for col, row in ((0, 0), (419, 187), (1279, 1023)):
            self.assertEqual(blob_cell(*blob_point(col, row)), (col, row))

    def test_wire_speed_is_milli_units(self):
        self.assertEqual(wire_speed(8.6), 8600)
        with self.assertRaises(ProtocolError):
            wire_speed(100)


class BlobTests(unittest.TestCase):
    def test_every_direction_round_trips(self):
        for direction, (dx, dy) in enumerate(DIRECTIONS):
            blob = encode_blob([(10, 10), (10 + dx, 10 + dy)])
            self.assertEqual(blob, bytes([(1 << 3) | direction]))
            self.assertEqual(decode_blob((10, 10), blob), [(10, 10), (10 + dx, 10 + dy)])

    def test_runs_pack_to_thirty_one_steps_per_byte(self):
        path = [(0, 0)]
        for _ in range(40):
            path.append((path[-1][0] + 1, 0))
        self.assertEqual(encode_blob(path), bytes([(31 << 3) | 4, (9 << 3) | 4]))
        self.assertEqual(len(decode_blob((0, 0), encode_blob(path))), 41)

    def test_direction_change_starts_a_new_byte(self):
        blob = encode_blob([(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)])
        self.assertEqual(blob, bytes([(2 << 3) | 4, (2 << 3) | 6]))

    def test_rejects_non_adjacent_and_degenerate_paths(self):
        with self.assertRaises(ProtocolError):
            encode_blob([(0, 0), (2, 0)])
        with self.assertRaises(ProtocolError):
            encode_blob([(0, 0), (0, 0)])
        with self.assertRaises(ProtocolError):
            encode_blob([(0, 0)])

    def test_rejects_zero_step_blob_byte(self):
        with self.assertRaises(ProtocolError):
            decode_blob((0, 0), bytes([4]))


class PayloadTests(unittest.TestCase):
    def test_layout_is_float4_length_blob_short2_uint32(self):
        segment = Segment(((0, 0), (3, 0)), bytes([(3 << 3) | 4]), 1.75, 0.25, 1.75, 0.25, 8600)
        payload = segment.payload(7)
        self.assertEqual(len(payload), 26 + len(segment.blob))
        self.assertEqual(decode_move(payload), (1.75, 0.25, 1.75, 0.25, segment.blob, 8600, 0, 7))

    def test_sync_wraps_and_never_regresses(self):
        sync = Sync()
        self.assertEqual([sync.next(), sync.next()], [1, 2])
        sync.adopt(40)
        self.assertEqual(sync.next(), 41)
        sync.adopt(10)
        self.assertEqual(sync.next(), 42)
        sync.adopt(0xFFFFFFFF)
        self.assertEqual(sync.next(), 0)


class ServerBlockTests(unittest.TestCase):
    def test_hard_bit_is_rejected_and_fake_bit_is_not(self):
        hard, fake = grid([0x10, 0, 0, 0]), grid([0x80, 0, 0, 0])
        self.assertTrue(server_blocked(hard, 1, 0))
        self.assertFalse(server_blocked(hard, 0, 0))
        self.assertFalse(server_blocked(fake, 0, 0))

    def test_out_of_node_counts_as_blocked(self):
        for cell in ((-1, 0), (0, -1), (4, 0), (0, 4)):
            self.assertTrue(server_blocked(grid([0] * 4), *cell))

    def test_plan_refuses_a_chunk_that_crosses_a_hard_block(self):
        with self.assertRaises(ProtocolError):
            plan([blob_point(0, 0), blob_point(1, 0), blob_point(2, 0)],
                 grid([0x10, 0, 0, 0]))


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = next((path for path in MAPS if path.exists()), None)
        if source is None:
            raise unittest.SkipTest('S610.smp is not available on this host')
        cls.grid = Grid.read(source)
        cls.start, cls.goal = (234.61, 93.90), (210, 178)
        cls.route = cls.grid.route(cls.start, cls.goal)
        cls.cells = path_cells(cls.route)

    def test_route_is_fully_walkable_by_the_server_rule(self):
        self.assertEqual(len(self.cells), 198)
        self.assertEqual(self.cells[0], (469, 187))
        self.assertEqual(self.cells[-1], (420, 356))
        self.assertFalse(any(server_blocked(self.grid, *cell) for cell in self.cells))

    def test_every_chunk_is_contiguous_and_covered_once(self):
        parts = chunks(self.cells, 12)
        self.assertEqual(parts[0][0], self.cells[0])
        self.assertEqual(parts[-1][-1], self.cells[-1])
        for before, after in zip(parts, parts[1:]):
            self.assertEqual(before[-1], after[0])
        rebuilt = [cell for part in parts for cell in part]
        self.assertEqual(len(rebuilt) - (len(parts) - 1), len(self.cells))
        self.assertEqual(set(rebuilt), set(self.cells))

    def test_planned_segments_are_accepted_in_sequence(self):
        segments = plan(self.route, self.grid, step_limit=12, speed=8600)
        self.assertTrue(segments)
        self.assertTrue(all(segment.speed != 8600 for segment in segments))
        self.assertTrue(all(len(segment.blob) == 1 for segment in segments))
        self.assertEqual(sum(segment.steps for segment in segments), len(self.cells) - 1)
        position = self.start
        for segment in segments:
            self.assertTrue(replica_accept(self.grid, position, segment.f1, segment.f2, segment.blob))
            position = segment.f1, segment.f2
        self.assertEqual(blob_cell(*position), self.cells[-1])

    def test_the_old_empty_blob_packet_is_rejected(self):
        self.assertFalse(replica_accept(self.grid, self.start, *blob_point(*self.cells[1]), b''))

    def test_one_packet_mode_reaches_the_same_cell(self):
        blob = encode_blob(self.cells)
        self.assertEqual(len(blob), 13)
        self.assertTrue(replica_accept(self.grid, self.start, *blob_point(*self.cells[-1]), blob))
        self.assertEqual(decode_blob(self.cells[0], blob)[-1], self.cells[-1])

    def test_chunk_size_does_not_change_the_destination(self):
        for limit in (1, 2, 4, 8, 16, 31, 64):
            segments = plan(self.route, self.grid, step_limit=limit)
            self.assertEqual(segments[-1].cells[-1], self.cells[-1])
            position = self.start
            for segment in segments:
                self.assertTrue(replica_accept(self.grid, position, segment.f1, segment.f2, segment.blob))
                position = segment.f1, segment.f2


if __name__ == '__main__':
    unittest.main()
