"""SMP2.0 half-unit collision grid, matched to V15 CNodeTemplate::IsBlock.

This handles static collision only. Dynamic doors/events still require normal
game triggers; a route must pause when live movement disagrees with the grid.
"""
from dataclasses import dataclass, field
import heapq
import itertools
import math
from pathlib import Path
from wire import Reader, ProtocolError


@dataclass
class Grid:
    origin_x: int
    origin_y: int
    width: int
    height: int
    cells: bytes
    obstacles: set = field(default_factory=set)

    @classmethod
    def read(cls, path):
        reader = Reader(Path(path).read_bytes())
        if reader.text() != 'SMP2.0':
            raise ProtocolError('Unsupported collision format')
        reader.text()  # original asset filename
        ox, oy, width, height, size = (reader.number(fmt) for fmt in ('h', 'h', 'H', 'H', 'i'))
        if not 0 < width <= 4096 or not 0 < height <= 4096 or size != width * height:
            raise ProtocolError('Invalid SMP dimensions/size')
        cells = reader.take(size)
        reader.end()
        return cls(ox, oy, width, height, cells)

    def cell(self, x, y):
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError('Non-finite coordinates')
        return math.floor((x - self.origin_x) * 2), math.floor((y - self.origin_y) * 2)

    def center(self, cell):
        return self.origin_x + (cell[0] + .5) / 2, self.origin_y + (cell[1] + .5) / 2

    def blocked_cell(self, cell, include_fake=True):
        if cell in self.obstacles:
            return True
        hx, hy = cell
        if hx <= 0 or hy < 0 or hx >= self.width * 2 or hy >= self.height * 2:
            return True
        linear = hy * self.width * 2 + hx
        mask = (0xC0 if include_fake else 0x40) >> ((hx & 3) * 2)
        return bool(self.cells[linear >> 2] & mask)

    def blocked(self, x, y, include_fake=True):
        return self.blocked_cell(self.cell(x, y), include_fake)

    def clear(self, cell, radius=.5):
        # Conservative square clearance; does not cut corners or pass narrow gaps.
        spread = math.ceil(radius * 2)
        return all(not self.blocked_cell((cell[0] + dx, cell[1] + dy))
                   for dy in range(-spread, spread + 1) for dx in range(-spread, spread + 1))

    def approach(self, point, radius=.5, limit=16):
        """The closest walkable cell centre to an authored spawn point."""
        cell = self.cell(*point)
        if self.clear(cell, radius):
            return self.center(cell)
        for ring in range(1, limit + 1):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    candidate = (cell[0] + dx, cell[1] + dy)
                    if self.clear(candidate, radius):
                        return self.center(candidate)
        raise ProtocolError('No collision-safe cell near target')

    def route(self, start, goal, radius=.5, max_expansions=50000):
        start_cell, goal_cell = self.cell(*start), self.cell(*goal)
        if not self.clear(start_cell, radius) or not self.clear(goal_cell, radius):
            raise ProtocolError('Route endpoint lacks collision clearance')
        sequence = itertools.count()
        frontier = [(0, next(sequence), start_cell)]
        cost, previous = {start_cell: 0}, {}
        closed = set()
        while frontier and len(closed) < max_expansions:
            _, _, current = heapq.heappop(frontier)
            if current in closed:
                continue
            closed.add(current)
            if current == goal_cell:
                cells = [current]
                while current != start_cell:
                    current = previous[current]
                    cells.append(current)
                return [start, *[self.center(cell) for cell in reversed(cells[:-1])], goal]
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                neighbor = current[0] + dx, current[1] + dy
                if neighbor in closed or not self.clear(neighbor, radius):
                    continue
                if dx and dy and (not self.clear((current[0] + dx, current[1]), radius) or
                                  not self.clear((current[0], current[1] + dy), radius)):
                    continue
                candidate = cost[current] + math.hypot(dx, dy)
                if candidate < cost.get(neighbor, math.inf):
                    previous[neighbor], cost[neighbor] = current, candidate
                    heuristic = math.dist(neighbor, goal_cell)
                    heapq.heappush(frontier, (candidate + heuristic, next(sequence), neighbor))
        raise ProtocolError('No bounded collision-safe route found')

    def line_clear(self, start, goal):
        count = max(1, math.ceil(math.dist(start, goal) * 8))
        return all(self.clear(self.cell(start[0] + (goal[0] - start[0]) * i / count,
                                        start[1] + (goal[1] - start[1]) * i / count))
                   for i in range(count + 1))
