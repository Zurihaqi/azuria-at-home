import subprocess
name='CNE_ZW_ZoneServerItemMallReceieveAttempt'
mangled=f'_ZN5lapis{len(name)}{name}7ExecuteEv'
cmd=['gdb','-batch','-ex','info address '+mangled,'-ex','disassemble '+mangled,'/root/hxsy/ZoneServer/ZoneServer']
r=subprocess.run(cmd,text=True,capture_output=True);open('/root/mall-claim-disassembly.txt','w').write(r.stdout+r.stderr)
print('symbol',mangled)
print('\n'.join(x for x in (r.stdout+r.stderr).splitlines() if 'call' in x or 'Symbol' in x or 'No symbol' in x)[:10000])
