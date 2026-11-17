"""Correct verified native AP parameters and synchronize missing server text."""
# Historical deployment: broad server T_* synchronization was rolled back.
# See docs/SOVEREIGN-V2.md before reusing; the active gear/AP corrections remain.
from pathlib import Path
import datetime,hashlib,json,re,shutil,sys
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT/'ops/runtime'))
import paramiko
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db';OUT=ROOT/'staging/sovereign-v2-final';OUT.mkdir(exist_ok=True)
def decode(data):return data.decode('cp950',errors='surrogateescape')
def rows(text):return {int(r[0]):r for c in re.split(r'(?m)(?=^\d+\|)',text)[1:] if len(r:=c.rstrip('\r\n').split('|'))>1}
def patched(text,changes):
 changes=changes.copy()
 def sub(m):
  row=changes.pop(int(m[1]),None);return '|'.join(row)+'\r\n' if row is not None else m[0]
 text=re.sub(r'(?ms)^(\d+)\|.*?(?=^\d+\||\Z)',sub,text)
 if changes:text=text.rstrip('\r\n')+'\r\n'+''.join('|'.join(r)+'\r\n' for r in changes.values())
 return text.encode('cp950',errors='surrogateescape')
ssh=paramiko.SSHClient();ssh.load_host_keys(str(ROOT/'private/known_hosts'))
key=paramiko.Ed25519Key.from_private_key_file(str(ROOT/'private/vm_ed25519'),password='""')
ssh.connect('127.0.0.1',port=22222,username='root',pkey=key,look_for_keys=False,allow_agent=False,timeout=10)
manifest={'server':[],'client':[],'server_text':{}}
try:
 with ssh.open_sftp() as sftp:
  server={n:decode(sftp.open('/root/hxsy/Data/db/'+n,'rb').read()) for n in ['S_Item.ini','S_Enchant.ini','T_Item.ini','T_ItemMall.ini','T_Enchant.ini','T_EquipSet.ini','T_Biology.ini','T_Title.ini','T_Mission.ini']}
  client={n:decode((CLIENT/n).read_bytes()) for n in ['C_Item.ini','C_Enchant.ini','T_Enchant.ini']}
  data={**server,**client};original=data.copy()
  for name in ['S_Enchant.ini','C_Enchant.ini']:
   mapping=rows(data[name]);changes={}
   for ident in [180003,180004,180006,180007,180008]:
    row=mapping[ident].copy()
    for slot in [8,15,22,29]:
     if row[slot]=='2155':
      assert row[slot+1]=='0' and int(row[slot+2])>0
      row[slot+1],row[slot+2],row[slot+3]=row[slot+2],'0',''
    changes[ident]=row
   common=changes[180003]
   for ident in range(180010,180020):
    assert ident not in mapping
    row=common.copy();row[0]=str(ident);row[5]+=' '+str(ident-180009);changes[ident]=row
   data[name]=decode(patched(data[name],changes))
  changes={};mapping=rows(data['T_Enchant.ini'])
  for ident in range(180010,180020):
   row=mapping[180003].copy();row[0]=str(ident);row[1]+=' '+str(ident-180009);changes[ident]=row
  data['T_Enchant.ini']=decode(patched(data['T_Enchant.ini'],changes))
  for name in ['S_Item.ini','C_Item.ini']:
   mapping=rows(data[name]);changes={}
   for ident,ench in zip(range(61587,61597),range(180010,180020)):
    row=mapping[ident].copy();assert row[21]=='180003';row[21]=str(ench);changes[ident]=row
   data[name]=decode(patched(data[name],changes))
  # Server may send names directly; fill gaps while preserving its existing translations.
  server_text={}
  for name in ['T_Item.ini','T_ItemMall.ini','T_Enchant.ini','T_EquipSet.ini','T_Biology.ini','T_Title.ini','T_Mission.ini']:
   reference=data['T_Enchant.ini'] if name=='T_Enchant.ini' else decode((CLIENT/name).read_bytes())
   localrows=rows(reference);remote=rows(server[name]);changes={}
   custom=set(range(61586,61597))|set(range(61600,61604))|set(range(180001,180020))
   if name=='T_EquipSet.ini':custom={1001,1002,1003}
   for ident,row in localrows.items():
    current=remote.get(ident)
    if current is None or ident in custom:changes[ident]=row;continue
    if len(current)!=len(row):continue
    merged=current.copy()
    for i in range(1,len(row)-1):
     if (not merged[i].strip() or merged[i].strip().lower() in ['err','error','(null)']) and row[i].strip():merged[i]=row[i]
    if merged!=current:changes[ident]=merged
   server_text[name]=patched(server[name],changes);manifest['server_text'][name]=len(changes)
  # Proven unnamed placeholders from the mass title unlock; never touch quest state.
  title_text=rows(decode((CLIENT/'T_Title.ini').read_bytes()))
  invalid=[ident for ident,row in rows(decode((CLIENT/'C_Title.ini').read_bytes())).items() if not row[1].strip() and (ident not in title_text or title_text[ident][1].startswith('Unused Title #'))]
  manifest['unused_title_ids']=invalid
  for name in ['S_Item.ini','S_Enchant.ini']:
   after=data[name].encode('cp950',errors='surrogateescape');(OUT/name).write_bytes(after)
   manifest['server'].append({'name':name,'before':hashlib.sha256(server[name].encode('cp950',errors='surrogateescape')).hexdigest(),'after':hashlib.sha256(after).hexdigest()})
  for name,after in server_text.items():
   target='server-'+name;(OUT/target).write_bytes(after)
   manifest['server'].append({'name':name,'payload':target,'before':hashlib.sha256(server[name].encode('cp950',errors='surrogateescape')).hexdigest(),'after':hashlib.sha256(after).hexdigest()})
  for name in ['C_Item.ini','C_Enchant.ini','T_Enchant.ini']:
   after=data[name].encode('cp950',errors='surrogateescape');(OUT/name).write_bytes(after)
   manifest['client'].append({'name':name,'before':hashlib.sha256((CLIENT/name).read_bytes()).hexdigest(),'after':hashlib.sha256(after).hexdigest()})
  (ROOT/'docs/sovereign-v2-final-manifest.json').write_text(json.dumps(manifest,indent=2))
  try:sftp.mkdir('/root/sovereign-v2-final')
  except OSError:pass
  sftp.put(str(ROOT/'docs/sovereign-v2-final-manifest.json'),'/root/sovereign-v2-final-manifest.json')
  sftp.put(str(ROOT/'ops/finish-sovereign-v2-guest.py'),'/root/finish-sovereign-v2-guest.py')
  for entry in manifest['server']:
   name=entry.get('payload',entry['name']);sftp.put(str(OUT/name),'/root/sovereign-v2-final/'+name)
 channel=ssh.get_transport().open_session();channel.set_combine_stderr(True);channel.exec_command('python3 /root/finish-sovereign-v2-guest.py')
 result=b''
 while True:
  block=channel.recv(32768)
  if not block:break
  result+=block
 assert channel.recv_exit_status()==0,result.decode(errors='replace')
 print(result.decode(errors='replace'))
 backup=ROOT/'private/client-original'/('sovereign-v2-final-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir()
 for e in manifest['client']:
  target=CLIENT/e['name'];assert hashlib.sha256(target.read_bytes()).hexdigest()==e['before'];shutil.copy2(target,backup/e['name'])
  with target.open('r+b') as out:out.write((OUT/e['name']).read_bytes());out.truncate()
 with ssh.open_sftp() as sftp:sftp.get('/root/sovereign-v2-final-report.json',str(ROOT/'docs/sovereign-v2-final-report.json'))
 print('Client AP corrections and independent per-piece passive IDs installed.')
finally:ssh.close()
