"""Small verified V15 player-packet layouts used by the lab prototype."""
import struct
from wire import Reader, ProtocolError


def first_inventory_item(payload):
    """Read the first occupied item of the first bag; not a full inventory parser."""
    data = Reader(payload)
    if data.number('B') == 0:
        return None
    size, index = data.number('h'), data.number('h')
    if not 0 <= size <= 256:
        raise ProtocolError('Unexpected inventory size')
    occupancy = data.take(data.number('H'))
    if len(occupancy) != (size + 7) // 8:
        raise ProtocolError('Invalid inventory occupancy length')
    slots = [slot for slot in range(size)
             if occupancy[slot // 8] & (0x80 >> (slot % 8))]
    if not slots:
        return None
    return index, slots[0], data.number('I')


def equip_from_inventory(bag, slot, equipment_page=0):
    # FromContainer, FromLoc (slot), FromIndex (bag), ToContainer,
    # ToLoc (-1 lets native item validation select a slot), ToIndex (gear page).
    return struct.pack('<hhhhhh', 0, slot, bag, 1, -1, equipment_page)
