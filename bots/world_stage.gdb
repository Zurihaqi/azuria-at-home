set pagination off
ptype lapis::CNC_CL_ClientGetWorldServers
ptype lapis::CNC_CL_ServerLoginWorld
ptype lapis::CNC_CL_ClientReceiveTicketToWorldServer
disassemble 'lapis::CNC_CL_ServerLoginWorld::Serialize(lapis::COutBinStream&)'
disassemble 'lapis::CNC_CL_ClientGetWorldServers::Serialize(lapis::COutBinStream&)'
disassemble 'lapis::CNC_CL_ClientReceiveTicketToWorldServer::Serialize(lapis::COutBinStream&)'
quit
