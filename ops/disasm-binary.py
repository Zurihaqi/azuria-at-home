"""Local ELF disassembler with symbol/string annotation for research."""
from pathlib import Path
import struct, sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

BIN = Path(__file__).resolve().parent.parent / 'staging/ultimate/hxsy/WorldServer/WorldServer'

def load(path=BIN):
    f = open(path, 'rb')
    f.seek(0x28); e_shoff, = struct.unpack('<Q', f.read(8))
    f.seek(0x3A); shent, shnum, shstr = struct.unpack('<HHH', f.read(6))
    secs = []
    for i in range(shnum):
        f.seek(e_shoff + i * shent)
        n, t, fl, a, o, s, l, inf, al, es = struct.unpack('<IIQQQQIIQQ', f.read(shent))
        secs.append((n, t, a, o, s, l, es))
    f.seek(secs[shstr][3]); st = f.read(secs[shstr][4])
    sn = {}
    for i, s in enumerate(secs):
        sn[st[s[0]:st.index(b'\0', s[0])].decode()] = s
    sym, sstr, text, ro = sn['.symtab'], sn['.strtab'], sn['.text'], sn['.rodata']
    f.seek(sym[3]); symtab = f.read(sym[4])
    f.seek(sstr[3]); strtab = f.read(sstr[4])
    f.seek(text[3]); code = f.read(text[4])
    funcs = []
    for i in range(len(symtab) // 24):
        no, inf2, o2, sh2, val, size = struct.unpack_from('<IBBHQQ', symtab, i * 24)
        if not size or (inf2 & 0xf) != 2:
            continue
        nm = strtab[no:strtab.index(b'\0', no)].decode(errors='replace')
        funcs.append((val, size, nm))
    funcs.sort()
    return f, code, text[2], funcs, symtab, strtab, sn

def func_index(funcs):
    by_start = {}
    lo_min = funcs[0][0]
    starts = [x[0] for x in funcs]
    return starts, funcs

def lookup(funcs, addr):
    import bisect
    starts = [v for v, _, _ in funcs]
    i = bisect.bisect_right(starts, addr) - 1
    if i >= 0:
        v, s, n = funcs[i]
        if v <= addr < v + s:
            return v, s, n
    return None

if __name__ == '__main__':
    f, code, tbase, funcs, symtab, strtab, sn = load()
    f.seek(sn['.rodata'][3]); rodata = f.read(sn['.rodata'][4]); rob = sn['.rodata'][2]
    def str_at(a):
        if rob <= a < rob + len(rodata):
            o = a - rob; e = rodata.find(b'\0', o)
            if o < e <= o + 120:
                try: return rodata[o:e].decode()
                except Exception: return None
        return None
    import bisect
    starts = [v for v, _, _ in funcs]
    target = int(sys.argv[1], 16)
    size = int(str(sys.argv[3]) if len(sys.argv) > 3 else str(funcs[bisect.bisect_right(starts, target) - 1][1]), 0)
    f.seek(sn['.text'][3] + (target - tbase)); chunk = f.read(size)
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    for ins in md.disasm(chunk, target):
        ann = ''
        for op in ins.operands:
            if op.type == 3 and op.mem.base == 41:  # rip
                v = ins.address + ins.size + op.mem.disp
                s = str_at(v)
                if s: ann += f'  ; "{s[:100]}"'
                li = lookup(funcs, v)
                if li and not s: ann += f'  ; {li[2]}'
            if op.type == 2:
                s = str_at(op.imm)
                li = lookup(funcs, op.imm) if not s else None
                if s: ann += f'  ; "{s[:100]}"'
                elif li: ann += f'  ; {li[2]}'
        fn = lookup(funcs, ins.address)
        print(f'{ins.address:08x} {ins.mnemonic:8} {ins.op_str}{ann}')
