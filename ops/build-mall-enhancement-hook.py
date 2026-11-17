"""Assemble a narrow post-creation hook using the build's ordinary upgrade APIs."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).parent/'runtime'))
from keystone import Ks,KS_ARCH_X86,KS_MODE_64
root=Path(__file__).resolve().parent.parent
address=0x16ba040
table=0x16bb000
mask=bytearray(65536)
for item in json.loads((root/'docs/gear-catalog-expanded.json').read_text())['items']:
 typ=item['type'];flags=0
 if typ in set(range(1,6))|set(range(7,25))|{37,38}:flags|=1
 if 1<=typ<=24:flags|=2
 mask[item['id']]=flags
assembly='''
push rax
push rcx
push rdx
push rsi
push rdi
push r8
push r9
push r10
push r11
push r15
test rax,rax
jz done
cmp word ptr [rbx+0x34],6
jne done
mov rcx,[rax+0x10]
test rcx,rcx
jz done
movzx ecx,word ptr [rcx+8]
mov edx,0x16bb000
test byte ptr [rdx+rcx],1
jz stars
mov r15d,30
fortify_loop:
mov edi,0x16807f0
mov rdi,[rdi]
mov rsi,r12
mov rdx,r14
movsx ecx,word ptr [rsp+0x90]
mov r8d,r13d
call 0x4b2c20
dec r15d
jnz fortify_loop
stars:
mov rax,[rsp+0x48]
mov rcx,[rax+0x10]
movzx ecx,word ptr [rcx+8]
mov edx,0x16bb000
test byte ptr [rdx+rcx],2
jz done
movzx ecx,word ptr [rax+0x40]
cmp ecx,2
je star_ok
cmp ecx,3
je star_ok
cmp ecx,5
je star_ok
cmp ecx,6
jne done
star_ok:
mov word ptr [rax+0xc8],5
mov edi,0x16807f0
mov rdi,[rdi]
mov rsi,r12
mov rdx,rax
call 0x4a9da0
mov rax,[0x16902a0]
mov rdi,[rax+0x40]
mov esi,[r12+0x38]
mov edx,r13d
movsx ecx,word ptr [rsp+0x90]
mov r8d,5
call 0x8a2620
mov rax,[0x16902a0]
mov rdi,[rax+0x18]
mov esi,[r12+0x38]
call 0x88dc10
mov edi,32
call 0xdf0a40
mov qword ptr [rax],0xf2a9d8
mov qword ptr [rax+0x10],0xf2aa58
mov qword ptr [rax+0x18],0
mov [rax+8],r13w
mov cx,[rsp+0x90]
mov [rax+0xa],cx
mov word ptr [rax+0xc],5
mov rdi,r12
lea rsi,[rax+0x10]
mov edx,1
call 0x609650
done:
pop r15
pop r11
pop r10
pop r9
pop r8
pop rdi
pop rsi
pop rdx
pop rcx
pop rax
ret
'''
# Build one copy per site, replacing RET with original test/move and a jump back.
blobs=[]
for site in [0x7c787f,0x7c7f10]:
 asm=assembly.rsplit('ret',1)[0]+f'test rax,rax\nmov rbp,rax\njmp {site+6:#x}\n'
 encoded,_=Ks(KS_ARCH_X86,KS_MODE_64).asm(asm,addr=address+sum(len(x) for x in blobs))
 blobs.append(bytes(encoded))
code=b''.join(blobs)
assert address+len(code)<table
(root/'ops/mall-enhancement-code.bin').write_bytes(code)
(root/'ops/mall-enhancement-mask.bin').write_bytes(mask)
manifest={'code_address':address,'table_address':table,'sites':[{'site':0x7c787f,'target':address},{'site':0x7c7f10,'target':address+len(blobs[0])}],
          'code_size':len(code),'fortification_cap':30,'star_cap':5,'scope':'Item Mall category 6, eligible catalog equipment only'}
(root/'docs/mall-enhancement-hook.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
