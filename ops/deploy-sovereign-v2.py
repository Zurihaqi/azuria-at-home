"""Coordinate reviewed VM and client updates with independent backups."""
from pathlib import Path
import datetime,hashlib,json,re,shutil,sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'ops/runtime'))
import paramiko
manifest=json.loads((ROOT/'docs/sovereign-v2-manifest.json').read_text())
payload=ROOT/'staging/sovereign-v2'
client=ROOT/'client/Requiem Aurakingdom/data/db'
def rows(data):
 return {int(r[0]):r for c in re.split(r'(?m)(?=^\d+\|)',data.decode('cp950',errors='surrogateescape'))[1:] if len(r:=c.rstrip('\r\n').split('|'))>1}
for path in [client/'C_ItemMall.ini',ROOT/'staging/ultimate/hxsy/Data/db/S_ItemMall.ini']:
 assert not set(range(61600,61604)).intersection(rows(path.read_bytes())),path
for e in manifest['files']:
 assert hashlib.sha256((payload/e['name']).read_bytes()).hexdigest()==e['after_sha256']
 if not e['name'].startswith('S_'):
  assert hashlib.sha256((client/e['name']).read_bytes()).hexdigest()==e['before_sha256'],e['name']
  before=rows((client/e['name']).read_bytes());after=rows((payload/e['name']).read_bytes())
  assert set(before)<=set(after)
  if e['name'].startswith('T_'):
   for ident,original in before.items():
    if ident in set(range(61586,61597))|{180001,180002}:continue
    if len(original)>1 and original[1].strip() and original[1].strip().lower() not in ['err','error','(null)']:
     assert after[ident][1]==original[1],(e['name'],ident)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=ROOT/'private/client-original'/('sovereign-v2-'+stamp);backup.mkdir()
for e in manifest['files']:
 if not e['name'].startswith('S_'):shutil.copy2(client/e['name'],backup/e['name'])
ssh=paramiko.SSHClient();ssh.load_host_keys(str(ROOT/'private/known_hosts'))
key=paramiko.Ed25519Key.from_private_key_file(str(ROOT/'private/vm_ed25519'),password='""')
ssh.connect('127.0.0.1',port=22222,username='root',pkey=key,look_for_keys=False,allow_agent=False,timeout=10)
try:
 with ssh.open_sftp() as sftp:
  try:sftp.mkdir('/root/sovereign-v2')
  except OSError:pass
  sftp.put(str(ROOT/'docs/sovereign-v2-manifest.json'),'/root/sovereign-v2-manifest.json')
  sftp.put(str(ROOT/'ops/sovereign-v2-guest.py'),'/root/sovereign-v2-guest.py')
  for e in manifest['files']:
   if e['name'].startswith('S_'):sftp.put(str(payload/e['name']),'/root/sovereign-v2/'+e['name'])
 channel=ssh.get_transport().open_session();channel.set_combine_stderr(True);channel.exec_command('python3 /root/sovereign-v2-guest.py')
 output=b''
 while True:
  part=channel.recv(32768)
  if not part:break
  output+=part
 code=channel.recv_exit_status();print(output.decode(errors='replace'));assert code==0,'Guest deployment failed; client unchanged'
 try:
  for e in manifest['files']:
   if not e['name'].startswith('S_'):
    with (client/e['name']).open('r+b') as out:out.write((payload/e['name']).read_bytes());out.truncate()
 except Exception:
  for e in manifest['files']:
   if not e['name'].startswith('S_'):shutil.copy2(backup/e['name'],client/e['name'])
  raise
 with ssh.open_sftp() as sftp:sftp.get('/root/sovereign-v2-deployment.json',str(ROOT/'docs/sovereign-v2-deployment.json'))
 (ROOT/'docs/sovereign-v2-client.json').write_text(json.dumps({'backup':str(backup),'files':[e['name'] for e in manifest['files'] if not e['name'].startswith('S_')]},indent=2))
 print('Client updates complete; native loader checks pending.')
finally:ssh.close()
