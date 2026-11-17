set pagination off
set confirm off
python
import gdb, re
for name in ('lapis::CNE_CZ_ZoneServerMissionGoto::Deserialize(lapis::CInBinStream&)',
             'lapis::CNE_CZ_ZoneServerMissionGoto::Execute()',
             'lapis::CNC_CZ_ClientGoto::Serialize(lapis::COutBinStream&)'):
    print('\nFUNCTION ' + name)
    output = gdb.execute("disassemble '" + name + "'", to_string=True).splitlines()
    for line in output:
        # Keep real instructions and demangled call targets; trim repeated symbol names.
        line = re.sub(r' <[^>]*>:', ':', line)
        print(line)
end
quit
