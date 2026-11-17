import asyncio
from pathlib import Path
import struct
import math
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wire import Connection, ProtocolError, RC4, Reader
from navigation import Grid


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    def test_rc4_known_vector_and_stream_continuity(self):
        self.assertEqual(RC4(b'Key').crypt(b'Plaintext').hex(), 'bbf316e8d940af0ad3')
        key, plain = b'abcde', b'fragmented stream'
        split = RC4(key)
        self.assertEqual(split.crypt(plain[:3]) + split.crypt(plain[3:]), RC4(key).crypt(plain))

    async def test_partial_tcp_reads_preserve_frame(self):
        stream = asyncio.StreamReader()
        conn = Connection(stream, None)
        conn.rx = RC4(b'abcde')
        frame = struct.pack('<h', 6) + RC4(b'abcde').crypt(struct.pack('<HI', 67, 12345))
        task = asyncio.create_task(conn.receive())
        for value in frame:
            stream.feed_data(bytes([value]))
            await asyncio.sleep(0)
        self.assertEqual(await task, (67, struct.pack('<I', 12345)))

    async def test_reject_invalid_frame_lengths_before_reading_payload(self):
        for length in (-1, 0, 1, 8193, 32767):
            with self.subTest(length=length):
                stream = asyncio.StreamReader()
                stream.feed_data(struct.pack('<h', length))
                conn = Connection(stream, None)
                conn.rx = RC4(b'abcde')
                with self.assertRaises(ProtocolError):
                    await conn.receive()

    async def test_disconnect_mid_frame(self):
        stream = asyncio.StreamReader()
        stream.feed_data(struct.pack('<h', 10) + b'x')
        stream.feed_eof()
        conn = Connection(stream, None)
        conn.rx = RC4(b'abcde')
        with self.assertRaisesRegex(ProtocolError, 'closed'):
            await conn.receive()

    def test_reject_truncated_string_and_trailing_data(self):
        with self.assertRaises(ProtocolError):
            Reader(b'\xff\xffx').text()
        with self.assertRaises(ProtocolError):
            Reader(b'x').end()


class NavigationTests(unittest.TestCase):
    def setUp(self):
        # 8 x 8 world units, 16 x 16 half-unit cells.
        self.grid = Grid(0, 0, 8, 8, bytes(64))

    def mark(self, x, y):
        hx, hy = self.grid.cell(x, y)
        cells = bytearray(self.grid.cells)
        index = (hy * self.grid.width * 2 + hx) >> 2
        cells[index] |= 0x40 >> ((hx & 3) * 2)
        self.grid.cells = bytes(cells)

    def test_native_half_cell_bit_order(self):
        for x in (.25, .75, 1.25, 1.75):
            grid = Grid(0, 0, 2, 2, bytes(4))
            self.grid = grid
            self.mark(x, .25)
            for other in (.25, .75, 1.25, 1.75):
                self.assertEqual(grid.blocked(other, .25), other == x or other == .25)

    def test_path_routes_around_wall(self):
        for half_y in range(2, 12):
            self.mark(3.25, half_y / 2 + .25)
        route = self.grid.route((1.25, 2.25), (5.25, 2.25), radius=0)
        self.assertGreater(sum(math.dist(a, b) for a,b in zip(route, route[1:])), 4)
        self.assertTrue(all(not self.grid.blocked(*point) for point in route))
        self.assertTrue(any(point[1] > 5.5 or point[1] < 1 for point in route))

    def test_reject_blocked_endpoint_and_nonfinite_position(self):
        self.mark(2.25, 2.25)
        with self.assertRaises(ProtocolError):
            self.grid.route((2.25, 2.25), (5.25, 5.25), radius=0)
        with self.assertRaises(ValueError):
            self.grid.cell(float('nan'), 1)


if __name__ == '__main__':
    unittest.main()
