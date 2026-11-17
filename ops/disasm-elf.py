"""Disassemble a function from an ELF binary with symbol/string annotations.

Usage: python ops/disasm-elf.py <binary> <address-hex> [size] [--all]
--all includes PLT/interp; address resolves symbol automatically when size omitted.
"""
from pathlib import Path
import bisect, struct, sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from capstone import Cs, CS_ARCH_X86, CS_MODE_64


def load(path):
    f = open(path, 'rb')
    f.seek(0x28); e_shoff, = struct.unpack('<Q', f.read(8))
    f.seek(0x3A); shent, shnum, shstr = struct.unpack('<HHH', f.read(6))
    secs = []
    for i in range(shnum):
        f.seek(e_shoff + i * shent)
        n, t, fl, a, o, s, l, inf, al, es = struct.unpack('<IIQQQQIIQQ', f.read(shent))
        secs.append((n, t, a, o, s, l, es))
    f.seek(secs[shstr][3]); st = f.read(secs[shstr][4])
    sn = {st[s[0]:st.index(b'\0', s[0])].decode(): s for s in secs}
    return f, sn


def main():
    binp = sys.argv[1]
    addr = int(sys.argv[2], 16)
    size = int(sys.argv[3], 0) if len(sys.argv) > 3 else None
    f, sn = load(binp)
    sym = sn.get('.symtab')
    funcs = []
    if sym:
        f.seek(sym[3]); symtab = f.read(sym[4])
        strtab = sn['.strtab']
        f.seek(strtab[3]); names = f.read(strtab[4])
        for i in range(len(symtab) // 24):
            no, inf2, o2, sh2, val, sz = struct.unpack_from('<IBBHQQ', symtab, i * 24)
            if not sz or (inf2 & 0xf) != 2:
                continue
            funcs.append((val, sz, names[no:names.index(b'\0', no)].decode(errors='replace')))
        funcs.sort()
    text = sn['.text']
    size = size or next(sz for v, sz, n in funcs if v <= addr < v + sz)
    f.seek(text[3] + (addr - text[2])); code = f.read(size)
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    ann = {}
    for secname in ('.rodata',):
        sec = sn.get(secname)
        if sec:
            f.seek(sec[3]); data = f.read(sec[4])

            def str_at(a, sec=sec, data=data):
                if sec[2] <= a < sec[2] + len(data):
                    o = a - sec[2]; e = data.find(b'\0', o)
                    if 0 <= e - o <= 200:
                        return data[o:e]
                return None
            ann = set()
            for i in range(len(data)):
                pass
    def resolve(v):
        for val, sz, n in funcs:
            if val <= v < val + sz:
                return n
        return None
    outf = sys.stdout
    twrite = lambda s: (outf.buffer.write if hasattr(outf, 'buffer') else outf)(s)
    for ins in md.disasm(code, addr):
        note = ''
        try:
            for op in ins.operands:
                if op.type == 3 and op.mem.base == 41:
                    v = ins.address + ins.size + op.mem.disp
                    for secn in ('.rodata', '.data', '.data.rel.ro'):
                        sec = sn.get(secn)
                        if sec and sec[2] <= v < sec[2] + sec[4]:
                            f.seek(sec[3] + (v - sec[2]))
                            raw = f.read(120)
                            e = raw.find(b'\0')
                            if 0 <= e <= 100:
                                try:
                                    low = raw[:e].lower()
                                    if all(0x20 <= ch < 0x7f for ch in raw[:e]):
                                        s = raw[:e].decode()
                                        if sum(ch.isalnum() for ch in s) >= len(s) // 2:
                                            note += f'  ; "{s[:90]}"'
                                except Exception:
                                    pass
                            break
                    fn = resolve(v)
                    if fn and not note:
                        note = f'  ; {fn}'
        except Exception:
            pass
        fn = resolve(ins.address)
        head = f'{ins.address:08x} '
        if fn and fn != resolve(ins.address - 1):
            head += f'\n== {fn}\n{ins.address:08x} '
        line = f'{head}{ins.mnemonic:8} {ins.op_str}{note}\n'
        twrite(line.encode('utf-8', 'replace'))


if __name__ == '__main__':
    main()
