"""Authored public-map routing; native entry conditions remain authoritative."""
from collections import deque
import math
import struct
import time
import asyncio
from wire import ProtocolError


def route(graph, start, target, available, blocked, now=None):
    now = time.monotonic() if now is None else now
    queue = deque([(start, [])])
    visited = {start}
    while queue:
        current, path = queue.popleft()
        if current == target:
            return path
        for edge in graph.get(str(current), []):
            destination = edge['target']
            if (destination in available and destination not in visited
                    and blocked.get((current, edge['event']), 0) <= now):
                visited.add(destination)
                queue.append((destination, path + [edge]))
    return None


async def cross(edge, get_node, get_position, approach, walk, send, wait_ready):
    old = get_node()
    await walk(approach(tuple(edge['region'][:2])))
    if get_node() != old:
        await wait_ready()
        return True
    if math.dist(get_position(), edge['region'][:2]) > edge['region'][2] + 1:
        raise ProtocolError('Could not reach the normal portal trigger')
    await send('LeaveShop')
    await send('TalkToNPC', struct.pack('<I', 0))
    # CheckNodeExit carries the authored gateway *trigger* id (gateway_area
    # column 7); the native handler keys (node << 16) | trigger in its area
    # table. The gateway row id (41) is rejected as "not a valid event area".
    # Flag 0 fires the area's condition-0 ("step on") event, which performs
    # the transport; flag 1 only fires condition-1 ("step off") entries.
    await send('CheckNodeExit', struct.pack('<hhi', edge.get('trigger', edge['event']), 0, 0))
    await asyncio.sleep(.3)
    if get_node() == old:
        await send('TriggerNodeEvent', struct.pack('<H', edge['event']))
    for _ in range(60):
        if get_node() != old:
            await wait_ready()
            return True
        await asyncio.sleep(.25)
    return False
