"""NPC dialogue, mission-list and mission-state wire formats.

Everything here is a direct reading of the ZoneServer serializers:

    ClientDisplayDialogView  i32, i16 count, count * (i32 index, string, i16 kind)
    ClientEnterMissionList   i32 ui_kind, i32 quest, i32 npc, i32 complete
    ClientMissionStates      i16 count, count * (u16 quest, u16 state)
    ClientUpdateMissionState i8 kind, u64 quest, u16 state, i16 progress[4]

`ui_kind` is 1 for an offer list and 2 for a turn-in list. `ReplyDialog` is the
*position* of the option in the displayed list, not the authored option index,
which is why option positions are computed rather than sent through.

`Session` buffers every observed packet so a caller can wait for one shape
without stealing packets another part of the bot still needs.
"""
import asyncio
from dataclasses import dataclass
import struct
import time
from wire import ProtocolError, Reader


OFFER, TURN_IN = 1, 2
QUERY, ACCEPT, COMPLETE = 9, 1, 2
ACTIVE, READY, FINISHED = 3, 4, 1


@dataclass(frozen=True)
class DialogOption:
    index: int
    text: str
    kind: int


@dataclass(frozen=True)
class DialogView:
    ident: int
    options: tuple
    kind: int = 0
    npc: int = 0


def parse_dialog(payload):
    data = Reader(payload)
    ident = data.number('i')
    options = tuple(DialogOption(data.number('i'), data.text(), data.number('h'))
                    for _ in range(data.number('h')))
    # The serializer ends with a dialog type and the speaking NPC; older
    # captures stop after the options, so both tails are accepted.
    kind = data.number('b') if data.offset + 1 <= len(data.data) else 0
    npc = data.number('i') if data.offset + 4 <= len(data.data) else 0
    return DialogView(ident, options, kind, npc)


def parse_mission_list(payload):
    # ZoneServer writes `CNC_CZ_ClientEnterMissionList` as short Type, int
    # MissionID, int NpcID, short CompleteNum (0x677870), so a list is 12 bytes.
    # Keep the older 16-byte shape working for buffers captured before that
    # serializer was decoded.
    if len(payload) == 12:
        return struct.unpack('<hiih', payload)
    if len(payload) == 16:
        return struct.unpack('<iiii', payload)
    raise ProtocolError('Unexpected EnterMissionList length')


def parse_mission_states(payload):
    """First (normal) mission-state section; later sections belong to other maps."""
    data = Reader(payload)
    states = {}
    for _ in range(data.number('h')):
        quest, state = data.number('H'), data.number('H')
        states[quest] = state
    return states


def parse_state_update(payload):
    if len(payload) != 19:
        raise ProtocolError('Unexpected UpdateMissionState length')
    kind, quest, state, *progress = struct.unpack('<bQHhhhh', payload)
    return kind, quest, state, tuple(progress)


def option_for_quest(view, quest):
    """Position in the displayed list whose text names this quest."""
    wanted = str(int(quest))
    for position, option in enumerate(view.options):
        if option.text.strip() == wanted:
            return position
    for position, option in enumerate(view.options):
        if wanted in option.text.split():
            return position
    return None


class Session:
    """Packet buffer that lets one waiter block on a packet name."""

    WATCHED = (
        'DisplayDialogView', 'EnterMissionList', 'MissionStates',
        'UpdateMissionState', 'PutItemIntoInventory', 'SwitchItemLocationOK',
        'ItemUseOK', 'ClientTextOutputIndex', 'ClientCommandFailReturn',
    )

    def __init__(self, send, report=print):
        self.send = send
        self.report = report
        self.buffers = {}
        self.states = {}
        self.progress = {}
        self.personal = {}
        self.dirty = asyncio.Event()

    def observe(self, name, payload):
        if name == 'MissionStates':
            try:
                self.states.update(parse_mission_states(payload))
                data = Reader(payload)
                for _ in range(data.number('h')):
                    data.take(4)
                if data.offset < len(data.data):
                    for _ in range(data.number('h')):
                        data.take(4)
                    for _ in range(data.number('h')):
                        key, value = data.number('Q'), data.number('H')
                        self.personal[key] = value
            except ProtocolError:
                pass
        elif name == 'UpdateMissionState':
            try:
                kind, quest, state, progress = parse_state_update(payload)
            except ProtocolError:
                pass
            else:
                if kind == 0:
                    self.states[quest] = state
                    self.progress[quest] = progress
                elif kind == 1:
                    self.personal[quest] = state
        buffer = self.buffers.setdefault(name, [])
        buffer.append(payload)
        # A waiter only ever needs the latest few; drop ancient unclaimed copies.
        del buffer[:-64]
        self.dirty.set()

    async def expect(self, name, predicate=lambda payload: True, timeout=15):
        deadline = time.monotonic() + timeout
        while True:
            self.dirty.clear()
            buffer = self.buffers.get(name, [])
            for index, payload in enumerate(buffer):
                if predicate(payload):
                    del buffer[index]
                    return payload
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError(f'Timed out waiting for {name}')
            try:
                await asyncio.wait_for(self.dirty.wait(), remaining)
            except asyncio.TimeoutError:
                raise ProtocolError(f'Timed out waiting for {name}') from None

    def take(self, name, predicate=lambda payload: True):
        """Return a buffered packet without waiting, or None."""
        buffer = self.buffers.get(name, [])
        for index, payload in enumerate(buffer):
            if predicate(payload):
                del buffer[index]
                return payload
        return None

    async def send_named(self, name, payload=b''):
        await self.send(name, payload)

    async def talk(self, actor):
        self.buffers['DisplayDialogView'] = []
        await self.send('TalkToNPC', struct.pack('<I', actor))
        return parse_dialog(await self.expect('DisplayDialogView'))

    async def choose(self, view, position):
        if not 0 <= position < len(view.options):
            raise ProtocolError(f'Dialog option {position} is out of range')
        await self.send('ReplyDialog', struct.pack('<h', position))

    async def mission(self, operation, quest, value=65535):
        await self.send('MissionListOp', struct.pack('<hiH', operation, quest, value))

    async def query(self):
        await self.send('QueryMissionStates')
        return parse_mission_states(await self.expect('MissionStates'))

    async def open_quest(self, actor, quest, ui_kind):
        """Walk the dialog until the server lists this quest for accept/turn-in."""
        view = await self.talk(actor)
        position = option_for_quest(view, quest)
        if position is None:
            raise ProtocolError(f'Quest {quest} is not in the NPC dialog')
        await self.choose(view, position)
        expected = (ui_kind, int(quest))
        payload = await self.expect('EnterMissionList',
                                    lambda raw: parse_mission_list(raw)[:2] == expected)
        return parse_mission_list(payload)

    async def open_board(self, quest, ui_kind):
        """Virtual mission board (`accept_npc == 0`): talk to actor 0 and query."""
        await self.send('TalkToNPC', struct.pack('<I', 0))
        await self.mission(QUERY, quest)
        expected = (ui_kind, int(quest))
        payload = await self.expect('EnterMissionList',
                                    lambda raw: parse_mission_list(raw)[:2] == expected)
        return parse_mission_list(payload)

    async def accept(self, actor, quest, timeout=15):
        if actor:
            await self.open_quest(actor, quest, OFFER)
        else:
            await self.open_board(quest, OFFER)
        await self.mission(ACCEPT, quest)
        # MissionServer can satisfy a whole objective inside the accept
        # interaction (1001 is ready the moment Andre's dialog closes), so both
        # the normal active state and an immediate ready state are successes.
        return await self.state(quest, (ACTIVE, READY), timeout)

    async def turn_in(self, actor, quest, timeout=15):
        _, _, _, complete = await self.open_quest(actor, quest, TURN_IN)
        if complete not in (0, 1):
            raise ProtocolError(f'Quest {quest}: unexpected completion flag {complete}')
        await self.mission(COMPLETE, quest)
        return await self.state(quest, FINISHED, timeout)

    def mission_state(self, quest):
        payload = self.take('UpdateMissionState',
                            lambda raw: parse_state_update(raw)[1] == quest)
        return None if payload is None else parse_state_update(payload)

    async def state(self, quest, expected, timeout=15):
        choices = expected if isinstance(expected, tuple) else (expected,)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.states.get(quest) in choices:
                return self.states[quest]
            await asyncio.sleep(.05)
        state, progress = self.states.get(quest), self.progress.get(quest)
        raise ProtocolError(f'Quest {quest}: expected state {choices}, '
                            f'saw state {state} progress {progress}')
