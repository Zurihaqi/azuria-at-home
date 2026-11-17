"""Build type-specific shop sections and patch only category 6's menu builder."""
from pathlib import Path
import collections, hashlib, json, re, struct, sys
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
import pefile, capstone

root = Path(__file__).resolve().parent.parent
client = root / 'client/Requiem Aurakingdom'
labels = {
 7:'Dual Blades',8:'Sword and Shield',9:'Axes',10:'Staves',11:'Dual Pistols',12:'Cannons',
 13:'Grimoires',14:'Harps',15:'Katars',16:'Bows',17:'Tachi',18:'Scythes',19:'Holy Swords',
 20:'Shurikens',21:'Lances',22:'Guitars',23:'Dragon Puppets',24:'Whips',
 1:'Helmets',2:'Body Armor',3:'Waistguards',4:'Gloves',5:'Boots',6:'Cloaks',
 37:'Necklaces',38:'Rings',39:'Trophies',40:'Gaia Emblems',42:'Sacred Souls',43:'Anima Crystals',
 31:'Weapon Costumes',32:'Head Costumes',33:'Face Costumes',34:'Body Costumes',35:'Back Costumes',36:'Weapon Transformations',
 7001:'Fishing Rods',7003:'Fishing Hats',7004:'Fishing Clothes',7005:'Fishing Gloves',
 7006:'Fishing Boots',7008:'Cooking Tools',70:'Eidolon Keys',41:'Mounts',90000:"Zrymund's Sovereign Set"}
source='docs/gear-catalog-custom.json' if '--custom' in sys.argv else 'docs/gear-catalog-expanded.json' if '--expanded' in sys.argv else 'docs/gear-catalog.json'
catalog = json.loads((root/source).read_text())
menu_type=lambda row:row.get('menu_type',row['type'])
labels={typ:label for typ,label in labels.items() if typ in {menu_type(r) for r in catalog['items']}}
assert set(labels) == {menu_type(r) for r in catalog['items']}
sections = [{'type':typ,'detail_type':i,'label_id':61000+i,'label':label}
            for i,(typ,label) in enumerate(labels.items(),1)]
details = {s['type']:s['detail_type'] for s in sections}
items = sorted(catalog['items'], key=lambda r:(details[menu_type(r)],r['required_level'],r['id']))
for i,item in enumerate(items,1001):
    item.update(detail_type=details[menu_type(item)],index=i)
counts = collections.Counter(menu_type(r) for r in items)
for section in sections:
    section['items'] = counts[section['type']]
    section['pages_at_six_items'] = (section['items']+5)//6
output = dict(marker=catalog['marker'],item_group=6,money_unit=1,price=1,
              special_price=0,sections=sections,items=items)
(root/'docs/gear-catalog-split.json').write_text(json.dumps(output,indent=2))

path=client/'game.bin'
backup=root/'private/client-original/game.pre-gear-categories.bin'
if not backup.exists():backup.write_bytes(path.read_bytes())
b=bytearray(backup.read_bytes()); pe=pefile.PE(data=b)
base=pe.OPTIONAL_HEADER.ImageBase
offset=lambda va:pe.get_offset_from_rva(va-base)
hook=0x9c5dea
assert b[offset(hook):offset(hook)+7] == bytes.fromhex('8d45f0508d4de0')
align=lambda x,a:(x+a-1)//a*a
section_rva=align(pe.sections[-1].VirtualAddress+pe.sections[-1].Misc_VirtualSize,pe.OPTIONAL_HEADER.SectionAlignment)
raw=align(len(b),pe.OPTIONAL_HEADER.FileAlignment)
code=bytearray()
for section in sections:
    # Same vector<int>::push_back call and stack locals as the original category 6.
    code += bytes.fromhex('c745f0')+struct.pack('<I',section['label_id'])
    code += bytes.fromhex('8d45f0508d4de0')
    pos=base+section_rva+len(code)
    code += b'\xe8'+struct.pack('<i',0x11e1230-(pos+5))
pos=base+section_rva+len(code)
code += b'\xe9'+struct.pack('<i',0x9c5f7e-(pos+5))
size=align(len(code),pe.OPTIONAL_HEADER.FileAlignment)
header=pe.sections[-1].get_file_offset()+40
assert header+40 <= pe.OPTIONAL_HEADER.SizeOfHeaders
b[header:header+40]=struct.pack('<8sIIIIIIHHI',b'.akshop',len(code),section_rva,size,raw,0,0,0,0,0x60000020)
struct.pack_into('<H',b,pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'),pe.FILE_HEADER.NumberOfSections+1)
struct.pack_into('<I',b,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),align(section_rva+len(code),pe.OPTIONAL_HEADER.SectionAlignment))
struct.pack_into('<I',b,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfCode'),pe.OPTIONAL_HEADER.SizeOfCode+size)
b.extend(b'\0'*(raw-len(b)));b.extend(code);b.extend(b'\0'*(size-len(code)))
b[offset(hook):offset(hook)+7]=b'\xe9'+struct.pack('<i',base+section_rva-(hook+5))+b'\x90\x90'
patched=pefile.PE(data=b)
struct.pack_into('<I',b,pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'),patched.generate_checksum())
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
instructions=list(md.disasm(bytes(code),base+section_rva))
assert sum(i.mnemonic=='call' and i.op_str=='0x11e1230' for i in instructions)==len(sections)
assert instructions[-1].mnemonic=='jmp' and instructions[-1].op_str=='0x9c5f7e'
path.write_bytes(b)

for filename in ['T_TextIndex.ini','C_TextIndex.ini']:
    target=client/'data/db'/filename
    saved=root/'private/client-original'/(filename+'.pre-gear-categories')
    if not saved.exists():saved.write_bytes(target.read_bytes())
    # Restore the original label for the previous Gear Improvement slot.
    data=saved.read_bytes()
    if filename.startswith('T_'):
        data=re.sub(rb'(?m)^3131\|[^\r\n]*',b'3131|Reshuffle|',data)
        data=re.sub(rb'(?m)^2176\|[^\r\n]*',b'2176|Gear Catalog|',data)
    else:
        data=re.sub(rb'(?m)^2176\|[^\r\n]*',b'2176|3|Gear Catalog|',data)
    for section in sections:
        assert not re.search(rb'(?m)^'+str(section['label_id']).encode()+rb'\|',data)
    data=data.rstrip(b'\r\n')+b'\r\n'
    for section in sections:
        prefix=f"{section['label_id']}|"+('3|' if filename.startswith('C_') else '')
        data+=(prefix+section['label']+'|\r\n').encode('ascii')
    target.chmod(0o666)
    with target.open('r+b') as stream:stream.write(data);stream.truncate()
report={'sections':len(sections),'items':len(items),'maximum_pages_per_section':max(s['pages_at_six_items'] for s in sections),
        'menu':'Item Mall -> AP -> Gear Catalog -> gear type','client_sha256':hashlib.sha256(b).hexdigest(),
        'client_backup':str(backup),'validation':'Static menu hook/calls and full catalog coverage checked; live test pending'}
(root/'docs/gear-categories-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
