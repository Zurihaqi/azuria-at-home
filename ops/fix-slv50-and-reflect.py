"""Repair proven next-level null lookup; add a native 100% reflection passive."""
from pathlib import Path
import datetime,hashlib,json,re,shutil,sys
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT/'ops/runtime'))
import paramiko
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db';OUT=ROOT/'staging/slv50-reflect';OUT.mkdir(exist_ok=True)
def dec(data):return data.decode('cp950',errors='surrogateescape')
def line(text,ident):
 found=re.findall(r'(?m)^'+str(ident)+r'\|[^\r\n]*',text);assert len(found)==1,(ident,len(found));return found[0].split('|')
def update(text,row):
 pattern=r'(?m)^'+row[0]+r'\|[^\r\n]*';addition='|'.join(row)
 if re.search(pattern,text):text,n=re.subn(pattern,lambda m:addition,text);assert n==1
 else:text=text.rstrip('\r\n')+'\r\n'+addition+'\r\n'
 return text
ssh=paramiko.SSHClient();ssh.load_host_keys(str(ROOT/'private/known_hosts'));key=paramiko.Ed25519Key.from_private_key_file(str(ROOT/'private/vm_ed25519'),password='""');ssh.connect('127.0.0.1',port=22222,username='root',pkey=key,look_for_keys=False,allow_agent=False)
manifest={'files':[],'level_recovery':149,'playable_cap':150,'reference_level':151,'reflection_id':180020}
try:
 with ssh.open_sftp() as sftp:
  original={n:sftp.open('/root/hxsy/Data/db/'+n,'rb').read() for n in ['S_Level.ini','S_Item.ini','S_Enchant.ini']}
  original.update({n:(CLIENT/n).read_bytes() for n in ['C_Level.ini','C_Item.ini','C_Enchant.ini','T_Item.ini','T_Enchant.ini']})
  for name,before in original.items():
   text=dec(before)
   if name in ['S_Level.ini','C_Level.ini']:
    assert not re.search(r'(?m)^151\|',text)
    row=line(text,150);assert len(row)==74
    row[0]='151';row[2]='151';row[11]='151';text=update(text,row)
   elif name in ['S_Enchant.ini','C_Enchant.ini']:
    assert not re.search(r'(?m)^180020\|',text)
    row=line(text,180004);assert len(row)==63
    row[0]='180020';row[5]="Zrymund's Sovereign Retribution";row[8:36]=['']*28
    row[8:11]=['2037','100','100'];row[57]='100% chance to reflect 100% of damage taken back to the attacker while the Sovereign whip is equipped.'
    text=update(text,row)
   elif name in ['S_Item.ini','C_Item.ini']:
    row=line(text,61586);assert row[21]=='180001;180002;180004';row[21]+=';180020';row[31]+=' Reflects 100% of damage taken.';text=update(text,row)
   elif name=='T_Item.ini':
    row=line(text,61586);assert len(row)==4;row[2]+=' Reflects 100% of damage taken.';text=update(text,row)
   elif name=='T_Enchant.ini':
    row=['180020',"Zrymund's Sovereign Retribution",'100% chance to reflect 100% of damage taken back to the attacker while the Sovereign whip is equipped.','','','',''];text=update(text,row)
   after=text.encode('cp950',errors='surrogateescape');(OUT/name).write_bytes(after)
   manifest['files'].append({'name':name,'before':hashlib.sha256(before).hexdigest(),'after':hashlib.sha256(after).hexdigest()})
  (ROOT/'docs/slv50-reflect-manifest.json').write_text(json.dumps(manifest,indent=2))
  try:sftp.mkdir('/root/slv50-reflect')
  except OSError:pass
  sftp.put(str(ROOT/'docs/slv50-reflect-manifest.json'),'/root/slv50-reflect-manifest.json')
  sftp.put(str(ROOT/'ops/fix-slv50-and-reflect-guest.py'),'/root/fix-slv50-and-reflect-guest.py')
  for e in manifest['files']:
   if e['name'].startswith('S_'):sftp.put(str(OUT/e['name']),'/root/slv50-reflect/'+e['name'])
 channel=ssh.get_transport().open_session();channel.set_combine_stderr(True);channel.exec_command('python3 /root/fix-slv50-and-reflect-guest.py');output=b''
 while True:
  block=channel.recv(32768)
  if not block:break
  output+=block
 assert channel.recv_exit_status()==0,output.decode(errors='replace')
 print(output.decode(errors='replace'))
 backup=ROOT/'private/client-original'/('slv50-reflect-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir()
 for e in manifest['files']:
  if e['name'].startswith('S_'):continue
  target=CLIENT/e['name'];assert hashlib.sha256(target.read_bytes()).hexdigest()==e['before'];shutil.copy2(target,backup/e['name'])
  with target.open('r+b') as out:out.write((OUT/e['name']).read_bytes());out.truncate()
 with ssh.open_sftp() as sftp:sftp.get('/root/slv50-reflect-report.json',str(ROOT/'docs/slv50-reflect-report.json'))
 print('Client reference row and reflection definitions installed. Client backup: '+str(backup))
finally:ssh.close()
