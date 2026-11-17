set pagination off
ptype lapis::CNC_CW_ServerHello
ptype lapis::CNC_CW_ServerReceiveTicket
ptype lapis::CNC_CW_ClientHello
ptype lapis::CNC_CW_ServerCreateCharacterData
ptype lapis::CNC_CW_ServerCreateCharacterName
ptype lapis::CNC_CW_ClientGetCharacters
disassemble 'lapis::CNC_CW_ServerReceiveTicket::Serialize(lapis::COutBinStream&)'
disassemble 'lapis::CNC_CW_ServerHello::Serialize(lapis::COutBinStream&)'
disassemble 'lapis::CNC_CW_ServerCreateCharacterData::Deserialize(lapis::CInBinStream&)'
quit
