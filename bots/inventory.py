"""Native inventory locations and item streams, including quest-item stacks.

For stackable items the native durability field stores the stack quantity.
Do not use stack_count to count equipment: its durability means wear instead.
"""
import asyncio
import struct

from game_packets import equip_from_inventory
from wire import ProtocolError, Reader
from item_stream import inventory as decode_inventory, item as decode_item


class Inventory:
    def __init__(self):
        self.slots = {}
        self.items = {}
        self.revision = 0

    def observe(self, name, payload):
        if name == 'EnterNodeInventory':
            items, _ = decode_inventory(payload)
            self.slots = {location: item.id for location, item in items.items() if item.id}
            self.items = {location: item for location, item in items.items() if item.id}
            self.revision += 1
        elif name == 'PutItemIntoInventory' and len(payload) >= 8:
            bag, slot, item = struct.unpack_from('<hhI', payload)
            if item:
                self.slots[(bag, slot)] = item
                # Truncated prefix fixtures can locate an item but cannot supply
                # an authoritative quantity. Never retain an old slot's count.
                self.items.pop((bag, slot), None)
                if len(payload) > 8:
                    data = Reader(payload[4:])
                    self.items[(bag, slot)] = decode_item(data)
            else:
                self.discard(bag, slot)
        elif name == 'ModifyItemDurability' and len(payload) == 10:
            # Serialize 0x4ddb70 + CheckAutoStackItem 0x49fe06: container,
            # slot, current quantity/durability, max durability, bag/page.
            container, slot, current, maximum, bag = struct.unpack('<hhhhh', payload)
            held = self.items.get((bag, slot)) if container == 0 else None
            if held is not None:
                held.durability, held.maximum_durability = current, maximum
        return None

    def stack_count(self, ident):
        """Count an explicitly stackable item from native quantities only."""
        return sum(max(0, held.durability) for held in self.items.values() if held.id == ident)

    async def refresh(self, send, timeout=8):
        """Wait for a fresh full snapshot, including existing stacks on reconnect."""
        before = self.revision
        await send('EnterNodeInventory', b'')
        deadline = asyncio.get_running_loop().time() + timeout
        while self.revision <= before:
            if asyncio.get_running_loop().time() >= deadline:
                raise ProtocolError('Quest inventory snapshot timed out')
            await asyncio.sleep(.05)

    def add(self, bag, slot, item):
        self.slots[(bag, slot)] = item
        self.items.pop((bag, slot), None)

    def first(self, item):
        for (bag, slot), held in sorted(self.slots.items()):
            if held == item:
                return bag, slot
        return None

    def discard(self, bag, slot):
        self.slots.pop((bag, slot), None)
        self.items.pop((bag, slot), None)

    def equip_payload(self, bag, slot, page=0):
        return equip_from_inventory(bag, slot, page)

    def require(self, item):
        location = self.first(item)
        if location is None:
            raise ProtocolError(f'Item {item} is not in the tracked inventory')
        return location
