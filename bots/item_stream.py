"""V15 native clone-item stream decoder, bounded by the enclosing packet."""
from dataclasses import dataclass
from wire import Reader, ProtocolError


# CBinCaptain fields in SCloneItemStream::Deserialize (0x6c1c50).
FIELDS = ('H','H','I','I','I','I','H','I','B','I','B','H','I','B','I','B',
          'i','I','I','B','I','B','I','B','I','B','h','q','q','h','H','I',
          *('h',) * 10, 'H','H','I','Q')


@dataclass
class Item:
    id: int
    durability: int = 0
    maximum_durability: int = 0
    flags: int = 0
    fields: tuple = ()


def item(data):
    ident = data.number('I')
    if ident == 0:
        return Item(0)
    durability, maximum = data.number('h'), data.number('h')
    data.text()  # Custom label; never written to public bot logs.
    flags = data.number('B')
    mask = int.from_bytes(data.take(7), 'little')
    if mask >> len(FIELDS):
        raise ProtocolError('Unknown clone-item optional fields')
    values = tuple(data.number(code) if mask & (1 << bit) else 0 for bit, code in enumerate(FIELDS))
    return Item(ident, durability, maximum, flags, values)


def inventory(payload):
    data = Reader(payload)
    count = data.number('B')
    if count > 16:
        raise ProtocolError('Invalid inventory bag count')
    slots = {}
    for _ in range(count):
        size, bag = data.number('h'), data.number('h')
        if not 0 <= size <= 256 or not 0 <= bag <= 16:
            raise ProtocolError('Invalid inventory bag dimensions')
        bits = data.take(data.number('H'))
        if len(bits) != (size + 7) // 8:
            raise ProtocolError('Invalid inventory occupancy bitmap')
        for slot in range(size):
            if bits[slot // 8] & (0x80 >> (slot % 8)):
                slots[bag, slot] = item(data)
    return slots, data


def equipment(payload):
    data = Reader(payload)
    pages = data.number('B')
    if pages > 16:
        raise ProtocolError('Invalid equipment page count')
    slots = {}
    for _ in range(pages):
        page, bits = data.number('b'), data.number('I')
        if not 0 <= page <= 16:
            raise ProtocolError('Invalid equipment page')
        for slot in range(32):
            if bits & (1 << slot):
                slots[page, slot] = item(data)
    return slots, data
