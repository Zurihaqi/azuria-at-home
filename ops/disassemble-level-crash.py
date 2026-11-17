from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT/'ops/runtime'))
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
p=ROOT/'client/Requiem Aurakingdom/game.bin';pe=pefile.PE(str(p),fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_32)
for address,size in [(0x808180,240)]:
 for i in md.disasm(pe.get_data(address-base,size),address):print(f'{i.address:08x} {i.mnemonic:7} {i.op_str}')
