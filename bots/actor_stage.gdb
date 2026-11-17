set pagination off
ptype lapis::CNC_CZ_ClientSeeMob
ptype lapis::CNC_CZ_ClientMoveChar
ptype lapis::CNC_CZ_ClientMigrationDone
ptype lapis::CNE_CZ_ZoneServerTalkToNPC
ptype lapis::CNE_CZ_ZoneServerQueryMissionStates
disassemble 'lapis::CNC_CZ_ClientSeeMob::Serialize(lapis::COutBinStream&)'
disassemble 'lapis::CNC_CZ_ClientMoveChar::Serialize(lapis::COutBinStream&)'
disassemble 'lapis::CPlayerFactory::MoveSelf(lapis::CCharacter*, float, float, float, float, std::vector<char, std::allocator<char> >&, short, short)'
quit
