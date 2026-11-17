"""Native potential-point (PP) trees: decode the server snapshot, build allocations.

Packets (verified against ZoneServer disassembly):

  CNC_CZ_ClientPotentialPointUpdate (9 bytes) - `B H H H h`:
    page (0 = attack tree, 1 = defense tree), the three slot levels and the
    page's own free-point budget. Two packets arrive per character refresh,
    one per page (CCharacter::NotifyRefreshAttr +1026/+1124).

  CNE_CZ_ZoneServerPotentialPointUpdate (4 bytes) - `B B B B`:
    mode byte (0 = UpdatePPAtk, nonzero = UpdatePPDef) followed by the points
    added to slots 1..3 of that page. CCharacter::UpdatePPAtk rejects the whole
    request unless 0 < total <= free budget and every slot stays <= 99, then
    spends the budget, refreshes attributes and saves the character to the DB.
  CNE_CZ_ZoneServerPotentialPointReset (1 byte): nonzero resets the attack
    tree when the mode byte is nonzero the request resets the defense tree
    (CNE handler: mode 0 -> ResetPPAtk, else ResetPPDef).

The slot-to-effect mapping is intentionally not asserted here; allocation
strategy lives with the caller and is verified against native behaviour.
"""
import struct

from wire import ProtocolError

PAGE_ATTACK, PAGE_DEFENSE = 0, 1


def decode_update(payload):
    """Decode ClientPotentialPointUpdate into a dict, or None for foreign bytes."""
    if len(payload) != 9:
        return None
    page, s1, s2, s3, free = struct.unpack('<BHHHh', payload)
    if page not in (PAGE_ATTACK, PAGE_DEFENSE) or not all(0 <= v <= 99 for v in (s1, s2, s3)):
        return None
    return dict(page=page, slots=(s1, s2, s3), free=free)


def build_allocation(page, slots):
    """Points to spend now: `slots` are per-slot additions on `page`.

    The request total must fit the page's free budget, each slot stays <= 99,
    and at least one slot gains points; the server rejects anything else
    (UpdatePPAtk +0/+5..+100).
    """
    additions = tuple(int(v) for v in slots)
    if len(additions) != 3 or any(v < 0 for v in additions) or not any(additions):
        raise ProtocolError('Invalid potential allocation')
    if page not in (PAGE_ATTACK, PAGE_DEFENSE):
        raise ProtocolError('Invalid potential page')
    for value in additions:
        if value > 99:
            raise ProtocolError('Potential slot allocation exceeds the native cap')
    return struct.pack('<BBBB', page, *additions)


class Allocator:
    """Allocate earned points and confirm changes from subsequent snapshots."""
    def __init__(self):
        self.pages = {}
        self.pending = {}

    def observe(self, view):
        page = view['page']
        self.pages[page] = view
        expected = self.pending.get(page)
        confirmed = expected is not None and all(
            actual >= planned for actual, planned in zip(view['slots'], expected))
        if confirmed:
            del self.pending[page]
        return confirmed

    def request(self, view):
        # Attack: DMG, then CRIT/SPD. Defense: HP, then DEF/EVA. Native
        # per-slot cap is 99; each page owns a separate free-point budget.
        if view['page'] in self.pending or view['free'] <= 0:
            return None
        remaining = view['free']
        additions = []
        for spent in view['slots']:
            take = min(remaining, 99 - spent)
            additions.append(take)
            remaining -= take
        if not any(additions):
            return None
        self.pending[view['page']] = tuple(a + b for a, b in zip(view['slots'], additions))
        return tuple(additions)

    def summary(self):
        return {str(page): dict(slots=list(view['slots']), free=view['free'],
                                awaiting_confirmation=page in self.pending)
                for page, view in self.pages.items()}
