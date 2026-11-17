set pagination off
python
import gdb, json, re
ids = {}
names = set(re.findall(r'CNetCommand<lapis::(CNC_\w+)>::NCID', gdb.execute('info variables NCID', to_string=True)))
for name in sorted(names):
    try:
        ids[name] = int(gdb.parse_and_eval('lapis::CNetCommand<lapis::' + name + '>::NCID'))
    except gdb.error as exc:
        ids[name] = str(exc)
print(json.dumps({k:v for k,v in ids.items() if any(x in k for x in ('ReceiveTicket','CreateCharacter','GetCharacters','Hello','Exception','CharPassword','LoginCharacter','VerifyCharacterName')) and k.startswith(('CNC_CW_', 'CNC_CL_'))}))
open('/run/pilot/' + ('world-protocol.json' if 'WorldServer' in gdb.current_progspace().filename else 'protocol.json'), 'w').write(json.dumps(ids))
end
detach
quit
