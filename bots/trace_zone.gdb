set pagination off
set confirm off
python
import gdb, json, struct, time
protocol = json.load(open('/run/pilot/zone-protocol.json'))
names = {v:k for k,v in protocol.items() if k.startswith('CNE_CZ_')}
output = open('/var/lib/ak-bot-lab/logs/client-gameplay.jsonl', 'a', buffering=1)
interfaces = {}
class TracePackets(gdb.Breakpoint):
    count = 0
    def stop(self):
        try:
            pointer = int(gdb.parse_and_eval('$rsi'))
            memory = gdb.selected_inferior()
            return_address, = struct.unpack('<Q', bytes(memory.read_memory(int(gdb.parse_and_eval('$rsp')), 8)))
            if return_address != 0xd1bc6c:
                return False
            interface = int(gdb.parse_and_eval('$rbp'))
            vtable, = struct.unpack('<Q', bytes(memory.read_memory(interface, 8)))
            if vtable not in interfaces:
                interfaces[vtable] = gdb.execute('info symbol ' + hex(vtable), to_string=True)
            if 'CPCInterface' not in interfaces[vtable]:
                return False
            begin, end = struct.unpack('<QQ', bytes(memory.read_memory(pointer, 16)))
            size = end - begin
            if not 2 <= size <= 8192:
                return False
            opcode, = struct.unpack('<H', bytes(memory.read_memory(begin, 2)))
            if opcode not in names or opcode in (49, 66, 67):
                return False
            row = {'time': time.time(), 'opcode': opcode, 'name': names[opcode], 'length': size - 2}
            if opcode == 71:
                def q(address):
                    return struct.unpack('<Q', bytes(memory.read_memory(address, 8)))[0]
                character = q(interface + 0x18)
                character_id, = struct.unpack('<I', bytes(memory.read_memory(character + 0x38, 4)))
                row['character_id'] = character_id
                for label, offset in (('inventory_keys', 0xc38), ('equipment_keys', 0xc68)):
                    keys, pending = [], [q(character + offset + 16)]
                    while pending and len(keys) < 20:
                        entry = pending.pop()
                        if entry:
                            keys.append(struct.unpack('<h', bytes(memory.read_memory(entry + 32, 2)))[0])
                            pending.extend((q(entry + 16), q(entry + 24)))
                    row[label] = sorted(keys)
            # No arbitrary payload dumps, chat, authentication or ticket logging.
            formats = {2:'hiH', 68:'hhhhhh', 71:'', 72:'h', 73:'I', 188:'hH', 252:'H'}
            if opcode in formats and struct.calcsize('<' + formats[opcode]) == size - 2:
                row['fields'] = struct.unpack('<' + formats[opcode], bytes(memory.read_memory(begin + 2, size - 2)))
            output.write(json.dumps(row) + '\n')
            self.count += 1
            if self.count >= 2000:
                self.enabled = False
        except (gdb.error, ValueError, struct.error):
            pass
        return False
TracePackets('*0xd1c610', internal=True)
class MovementFailure(gdb.Breakpoint):
    def __init__(self, address, cause):
        super().__init__(address, internal=True)
        self.cause = cause
    def stop(self):
        try:
            memory = gdb.selected_inferior()
            character = int(gdb.parse_and_eval('$rbx'))
            character_id, = struct.unpack('<I', bytes(memory.read_memory(character + 0x38, 4)))
            if character_id == 50000004:
                output.write(json.dumps({'time': time.time(), 'movement_failure': self.cause,
                    'character_id': character_id}) + '\n')
        except (gdb.error, ValueError, struct.error):
            pass
        return False
MovementFailure('*0x572685', 'movement_state_guard')
MovementFailure('*0x572860', 'no_move_state')
class NativeBarrierState(gdb.Breakpoint):
    previous = None
    def stop(self):
        try:
            memory = gdb.selected_inferior()
            def q(address):
                return struct.unpack('<Q', bytes(memory.read_memory(address,8)))[0]
            character = int(gdb.parse_and_eval('$rbx'))
            ident, = struct.unpack('<I', bytes(memory.read_memory(character + 0x38,4)))
            if ident not in (50000003, 50000004, 50000005):
                return False
            node = q(character + 0x40)
            pending, keys = [q(node + 0x2c8)], []
            while pending and len(keys) < 30:
                entry = pending.pop()
                if entry:
                    keys.append(struct.unpack('<h', bytes(memory.read_memory(entry + 32,2)))[0])
                    pending.extend((q(entry + 16),q(entry + 24)))
            keys.sort()
            if keys != self.previous:
                self.previous = keys
                output.write(json.dumps({'time':time.time(), 'diagnostic':'native_barriers',
                    'character_id':ident, 'active_blocks':keys}) + '\n')
                server = q(0x1685ea0)
                template_id, = struct.unpack('<I', bytes(memory.read_memory(q(node + 0x78) + 8,4)))
                available = []
                for area in range(1, 50):
                    entry = q(server + 0x710)
                    wanted = (template_id << 16) | area
                    for _ in range(32):
                        if not entry:
                            break
                        key, = struct.unpack('<I', bytes(memory.read_memory(entry + 32,4)))
                        if key == wanted:
                            available.append(area)
                            break
                        entry = q(entry + (16 if wanted < key else 24))
                output.write(json.dumps({'time':time.time(), 'diagnostic':'native_gateway_keys', 'template_id':template_id, 'area_ids':available}) + '\n')
        except (gdb.error, ValueError, struct.error):
            pass
        return False
NativeBarrierState('*0x572b67', internal=True)
print('Sanitized gameplay metadata trace ready; no authentication payloads.')
end
continue
detach
quit
