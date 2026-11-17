"""Authored, bounded ordinary-player tutorial feasibility steps, Sword/Shield only."""
import asyncio
import struct
import sys
from wire import Reader, ProtocolError
from game_packets import equip_from_inventory


class Tutorial:
    def __init__(self, connection, protocol, mobs, walk, logout, report=print, fight=None):
        self.connection, self.protocol, self.mobs = connection, protocol, mobs
        self.walk, self.logout = walk, logout
        self.report = report
        self.fight = fight
        self.events = asyncio.Queue(maxsize=128)
        self.states = {}
        self.allowed = {protocol['CNC_CZ_Client' + name] for name in (
            'EnterMissionList', 'DisplayDialogView', 'UpdateMissionState',
            'PutItemIntoInventory', 'SwitchItemLocationOK', 'MissionStates')}

    def observe(self, opcode, payload):
        if opcode == self.protocol['CNC_CZ_ClientMissionStates']:
            data = Reader(payload)
            for _ in range(data.number('h')):
                quest, state = data.number('H'), data.number('H')
                self.states[quest] = state
        if opcode == self.protocol['CNC_CZ_ClientUpdateMissionState']:
            kind, quest, state, *_ = struct.unpack('<bQHhhhh', payload)
            if kind == 0:
                self.states[quest] = state
        if opcode in self.allowed:
            try:
                self.events.put_nowait((opcode, payload))
            except asyncio.QueueFull:
                raise ProtocolError('Tutorial event queue overflow; paused')

    async def send(self, name, payload=b''):
        await self.connection.send(self.protocol['CNE_CZ_ZoneServer' + name], payload)

    async def wait(self, name, predicate=lambda p: True):
        opcode = self.protocol['CNC_CZ_Client' + name]
        async def receive():
            while True:
                command, payload = await self.events.get()
                if command == opcode and predicate(payload):
                    return payload
        return await asyncio.wait_for(receive(), 12)

    async def state(self, quest, expected):
        choices = expected if isinstance(expected, tuple) else (expected,)
        async def check():
            while self.states.get(quest) not in choices:
                await asyncio.sleep(.1)
        try:
            await asyncio.wait_for(check(), 12)
        except asyncio.TimeoutError:
            raise ProtocolError(f'Quest {quest}: expected state {choices}, received {self.states.get(quest)}')

    async def mission(self, operation, quest):
        await self.send('MissionListOp', struct.pack('<hiH', operation, quest, 65535))

    async def talk_quest(self, npc, quest, ui_kind):
        matches = [key for key, value in self.mobs.items() if value['template'] == npc]
        if len(matches) != 1:
            raise ProtocolError('Authored tutorial NPC unavailable: ' + str(npc))
        await self.send('TalkToNPC', struct.pack('<I', matches[0]))
        payload = await self.wait('DisplayDialogView')
        data = Reader(payload)
        data.number('i')
        options = [(data.number('i'), data.text(), data.number('h'))
                   for _ in range(data.number('h'))]
        choices = [i for i, value in enumerate(options) if value[1] == str(quest)]
        if len(choices) != 1:
            raise ProtocolError('Authored quest dialogue option unavailable: ' + str(quest))
        await self.send('ReplyDialog', struct.pack('<h', choices[0]))
        await self.wait('EnterMissionList', lambda p: struct.unpack('<hiih', p)[:2] == (ui_kind, quest))

    async def run(self):
        await self.send('QueryMissionStates')
        await self.wait('MissionStates')
        if self.states.get(1001) in (3, 4):
            return await self.frontlines()
        if '--tutorial-resume' in sys.argv:
            await self.walk((220.5, 101))
            return await self.frontlines()
        await self.send('TalkToNPC', struct.pack('<I', 0))
        await self.mission(9, 2001)
        await self.wait('EnterMissionList', lambda p: struct.unpack('<hiih', p)[:2] == (1, 2001))
        await self.mission(1, 2001)
        item = await self.wait('PutItemIntoInventory', lambda p: len(p) >= 8 and struct.unpack_from('<I', p, 4)[0] == 30275)
        bag, slot = struct.unpack_from('<hh', item)
        await self.state(2001, 3)
        await self.send('LeaveShop')
        await self.send('SwitchItemLocation', equip_from_inventory(bag, slot))
        result = await self.wait('SwitchItemLocationOK')
        if result[-1] != 1:
            raise ProtocolError('Tutorial starter equipment rejected')
        await self.state(2001, 4)
        await self.walk((220.5, 101))
        await self.talk_quest(10204, 2001, 2)
        await self.mission(2, 2001)
        await self.state(2001, 1)
        self.report('Tutorial checkpoint: starter weapon quest completed normally.', flush=True)
        await self.frontlines()

    async def frontlines(self):
        if self.states.get(1001) not in (3, 4):
            await self.talk_quest(10204, 1001, 1)
            await self.mission(1, 1001)
            await self.state(1001, (3, 4))
        await self.send('LeaveShop')
        await self.walk((211, 94))
        await self.talk_quest(10205, 1001, 2)
        await self.mission(2, 1001)
        await self.state(1001, 1)
        self.report('Tutorial checkpoint: Head to the Frontlines completed normally.', flush=True)
        await self.talk_quest(10205, 2008, 1)
        await self.mission(1, 2008)
        await self.state(2008, 3)
        await self.send('LeaveShop')
        await self.send('EnterNodeEquipAndSpell')
        self.report('Tutorial checkpoint: native combat quest accepted; combat driver remains pending.', flush=True)
        if self.fight:
            await self.fight()
        else:
            await self.logout()
