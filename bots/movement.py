"""Verified V15 MoveSelf encoding, matched to CPlayerFactory::MoveSelf.

Packet layout (CNE_CZ_ZoneServerMoveSelf):

    <ffff H  blob  hh I   =   f1 f2 f3 f4  blob_len  blob  facing  action  sync

The server takes the start cell as (int)(ch->x * 2), (int)(ch->y * 2) in world
half-cell units and walks `blob`: one byte is (steps << 3) | dir, steps in
1..31, dir indexing DIRECTIONS. Every visited half-cell is tested with
CNode::IsBlockGrid and the first hard block aborts the move. The walk must end
exactly on (int)(f1 * 2), (int)(f2 * 2); otherwise the packet needs
CNode::CheckLineOfMoveSelf(blob_end -> f1, 0.8f) to be clear or it is dropped.

f1, f2 is therefore the authoritative new position, while f3, f4 only marks the
destination used to compute isFinal. Facing is radians*1000 (ch+0x134), and
sync is a monotonic guard: MoveSelf is dropped when sync is below ch+0x35c,
a floor that every ClientResetCoord raises and echoes.
"""
from dataclasses import dataclass
import math
import struct
from wire import ProtocolError


# Decoder order shared by both binaries; the low three bits of a blob byte.
DIRECTIONS = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
MAX_STEPS = 31
HEADER = struct.Struct('<ffffH')
FOOTER = struct.Struct('<hhI')


def blob_cell(x, y):
    """World position to the half-cell the server derives with (int)(x * 2)."""
    return int(x * 2), int(y * 2)


def blob_point(col, row):
    """Centre of a world half-cell; the origin cancels out of the packet."""
    return col / 2 + .25, row / 2 + .25


def wire_speed(movement):
    """Legacy conversion helper; this packet field is facing, not movement speed."""
    value = round(movement * 1000)
    if not -32768 <= value <= 32767:
        raise ProtocolError(f'Movement speed out of wire range: {movement}')
    return value


def wire_heading(dx, dy):
    """Native ChangeFaceDir: (3*pi/2 - atan2(dy,dx)) modulo 2*pi, radians*1000."""
    if not all(math.isfinite(value) for value in (dx, dy)) or (dx == 0 and dy == 0):
        raise ProtocolError('Facing requires a finite, nonzero movement vector')
    return round(((1.5 * math.pi - math.atan2(dy, dx)) % math.tau) * 1000)


def server_blocked(grid, col, row):
    """CNode::IsBlockGrid with the hard bit only, for a world half-cell.

    Live scene barriers (`[dynamic_block]`) are absolute half-cells too. They are
    active only while their authored actor is alive, so the caller merges the
    live set into `grid.obstacles` before planning.
    """
    if (col, row) in grid.obstacles:
        return True
    x, y = col - 2 * grid.origin_x, row - 2 * grid.origin_y
    if x < 0 or y < 0 or x >= grid.width * 2 or y >= grid.height * 2:
        return True
    return bool(grid.cells[(y * grid.width * 2 + x) >> 2] & (0x40 >> ((x & 3) * 2)))


def encode_blob(cells):
    if len(cells) < 2:
        raise ProtocolError('MoveSelf blob needs at least one step')
    blob = bytearray()
    direction, steps = None, 0
    for (x0, y0), (x1, y1) in zip(cells, cells[1:]):
        dx, dy = x1 - x0, y1 - y0
        try:
            current = DIRECTIONS.index((dx, dy))
        except ValueError:
            raise ProtocolError(f'Non-adjacent MoveSelf step: {dx}, {dy}') from None
        if current == direction and steps < MAX_STEPS:
            steps += 1
            continue
        if direction is not None:
            blob.append((steps << 3) | direction)
        direction, steps = current, 1
    blob.append((steps << 3) | direction)
    return bytes(blob)


def decode_blob(start, blob):
    x, y = start
    cells = [(x, y)]
    for byte in blob:
        steps, direction = byte >> 3, byte & 7
        if not 1 <= steps <= MAX_STEPS:
            raise ProtocolError(f'Invalid MoveSelf step count: {steps}')
        dx, dy = DIRECTIONS[direction]
        for _ in range(steps):
            x, y = x + dx, y + dy
            cells.append((x, y))
    return cells


def path_cells(route):
    cells = []
    for x, y in route:
        cell = blob_cell(x, y)
        if not cells or cell != cells[-1]:
            cells.append(cell)
    if len(cells) < 2:
        raise ProtocolError('Route has no movement')
    return cells


def chunks(cells, step_limit=12, split_turns=False):
    """Split a cell path into contiguous chunks of at most step_limit steps."""
    if not 1 <= step_limit <= 31 * 255:
        raise ProtocolError(f'Invalid chunk step limit: {step_limit}')
    if len(cells) < 2:
        raise ProtocolError('Route has no movement')
    result, index = [], 0
    while index < len(cells) - 1:
        stop = min(index + step_limit, len(cells) - 1)
        if split_turns:
            direction = (cells[index+1][0]-cells[index][0], cells[index+1][1]-cells[index][1])
            for turn in range(index+1, stop):
                if (cells[turn+1][0]-cells[turn][0], cells[turn+1][1]-cells[turn][1]) != direction:
                    stop = turn
                    break
        result.append(tuple(cells[index:stop + 1]))
        index = stop
    return result


@dataclass(frozen=True)
class Segment:
    cells: tuple
    blob: bytes
    f1: float
    f2: float
    f3: float
    f4: float
    speed: int = 0
    unknown: int = 0

    @property
    def steps(self):
        return len(self.cells) - 1

    def payload(self, sync):
        return (HEADER.pack(self.f1, self.f2, self.f3, self.f4, len(self.blob))
                + self.blob + FOOTER.pack(self.speed, self.unknown, sync & 0xFFFFFFFF))

    def describe(self):
        return (f'{self.steps} steps from {self.cells[0]} to {self.cells[-1]} '
                f'as {len(self.blob)} blob bytes')


def plan(route, grid, step_limit=12, speed=0):
    """Turn a navigation route into server-validated MoveSelf segments."""
    cells = path_cells(route)
    result = []
    for chunk in chunks(cells, step_limit, split_turns=True):
        blob = encode_blob(chunk)
        if tuple(decode_blob(chunk[0], blob)) != chunk:
            raise ProtocolError('MoveSelf blob does not round-trip')
        blocked = [cell for cell in chunk if server_blocked(grid, *cell)]
        if blocked:
            raise ProtocolError(f'MoveSelf chunk crosses a hard block at {blocked[0]}')
        x, y = blob_point(*chunk[-1])
        facing = wire_heading(chunk[-1][0]-chunk[0][0], chunk[-1][1]-chunk[0][1])
        result.append(Segment(chunk, blob, x, y, x, y, facing))
    return result


def replica_accept(grid, position, f1, f2, blob):
    """Local replica of the CPlayerFactory::MoveSelf acceptance test."""
    walked = decode_blob(blob_cell(*position), blob)
    if any(server_blocked(grid, *cell) for cell in walked):
        return False
    return walked[-1] == blob_cell(f1, f2)


def decode_move(payload):
    """Parse an outbound MoveSelf payload for regression logs and traces."""
    if len(payload) < HEADER.size + FOOTER.size:
        raise ProtocolError('Truncated MoveSelf')
    f1, f2, f3, f4, length = HEADER.unpack_from(payload)
    if len(payload) != HEADER.size + length + FOOTER.size:
        raise ProtocolError('MoveSelf blob length mismatch')
    offset = HEADER.size
    blob = payload[offset:offset + length]
    speed, unknown, sync = FOOTER.unpack_from(payload, offset + length)
    return f1, f2, f3, f4, blob, speed, unknown, sync


class Sync:
    """Monotonic MoveSelf sync that never falls below the server's floor."""

    def __init__(self, value=0):
        self.value = value

    def adopt(self, server_value):
        self.value = max(self.value, server_value & 0xFFFFFFFF)

    def next(self):
        self.value = (self.value + 1) & 0xFFFFFFFF
        return self.value
