"""Bounded native party state for the explicitly requested Arden companion."""
from dataclasses import dataclass
import math
import struct
import time
from wire import Reader, ProtocolError


@dataclass
class Member:
    slot: int
    id: int
    name: str


class Party:
    def __init__(self):
        self.members = {}
        self.leader = None
        self.positions = {}
        self.pending_inviter = None

    def invitation(self, payload):
        data = Reader(payload)
        inviter = data.number('I')
        name = data.text()
        first, second, kind = [data.number('h') for _ in range(3)]
        data.end()
        self.pending_inviter = inviter
        # Native answer's first short is the RESPONSE result, not the notice's
        # metadata: 0 accepts; 1 rejects; 2/3 report unavailable/busy.
        return struct.pack('<hIhh', 0, inviter, kind, 1), name, (first,second,kind)

    def roster(self, payload):
        data = Reader(payload)
        count = data.number('h')
        if not 0 <= count <= 40:
            raise ProtocolError('Invalid party roster size')
        members = {}
        for _ in range(count):
            slot, server = data.number('h'), data.number('h')
            actor, name = data.number('I'), data.text()
            # Verified TeamAllMembersInfo serializer; non-navigation stats stay opaque.
            for code in ('i','i','i','i','h','h','h','H','i','i','h',
                         'i','i','i','i','q','q','q','i','h','b'):
                data.number(code)
            members[slot] = Member(slot,actor,name)
        leader_slot = data.number('h')
        data.end()
        self.members = members
        self.leader = members[leader_slot].id if leader_slot in members else None
        return self.leader

    def position(self, payload):
        if len(payload) != 14:
            raise ProtocolError('Unexpected party position length')
        actor, node, x, y = struct.unpack('<Ihff', payload)
        if not math.isfinite(x) or not math.isfinite(y):
            raise ProtocolError('Invalid party coordinates')
        self.positions[actor] = (node,x,y,time.monotonic())

    def move(self, actor, node, x, y):
        if any(m.id==actor for m in self.members.values()) and math.isfinite(x) and math.isfinite(y):
            self.positions[actor] = (node,x,y,time.monotonic())

    def leave(self, payload, self_id):
        if len(payload)!=3:
            raise ProtocolError('Unexpected party leave length')
        slot, reason = struct.unpack('<hb',payload)
        member=self.members.pop(slot,None)
        if member and member.id==self_id:
            self.members.clear();self.leader=None;self.positions.clear()
        elif member and member.id==self.leader:
            self.leader=None

    def destination(self, now=None):
        value=self.positions.get(self.leader)
        if value and (time.monotonic() if now is None else now)-value[3]<20:
            return value[:3]
        return None
