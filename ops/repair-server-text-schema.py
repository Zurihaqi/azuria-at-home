# Historical experiment: server T_* edits were rolled back after LoadOK failed.
# Client record normalization remains active. Do not rerun against the live VM.
from pathlib import Path
import datetime,json,re,shutil,sys,hashlib
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT/'ops/runtime'))
import paramiko
CLIENT=ROOT/'client/Requiem Aurakingdom/data/db'
def dec(data):return data.decode('cp950',errors='surrogateescape')
def rows(text):return {int(r[0]):r for c in re.split(r'(?m)(?=^\d+\|)',text)[1:] if len(r:=c.rstrip('\r\n').split('|'))>1}
def patch(text,changes):
 changes=changes.copy()
 def sub(m):
  row=changes.pop(int(m[1]),None);return '|'.join(row)+'\r\n' if row else m[0]
 text=re.sub(r'(?ms)^(\d+)\|.*?(?=^\d+\||\Z)',sub,text)
 return (text.rstrip('\r\n')+'\r\n'+''.join('|'.join(r)+'\r\n' for r in changes.values())).encode('cp950',errors='surrogateescape')
ssh=paramiko.SSHClient();ssh.load_host_keys(str(ROOT/'private/known_hosts'));key=paramiko.Ed25519Key.from_private_key_file(str(ROOT/'private/vm_ed25519'),password='""');ssh.connect('127.0.0.1',port=22222,username='root',pkey=key,look_for_keys=False,allow_agent=False)
backup=json.loads((ROOT/'docs/sovereign-v2-final-report.json').read_text())['backup'];report={};clientbackup=ROOT/'private/client-original'/('text-schema-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));clientbackup.mkdir()
try:
 with ssh.open_sftp() as sftp:
  for name in ['T_Item.ini','T_ItemMall.ini','T_Enchant.ini','T_EquipSet.ini','T_Biology.ini','T_Title.ini','T_Mission.ini']:
   target=CLIENT/name;clienttext=dec(target.read_bytes());expected=int(clienttext.split('|',1)[0])+1;mapping=rows(clienttext);normalized={}
   for ident,row in mapping.items():
    if ident>10 and len(row)==expected-1:normalized[ident]=row+['']
    if len(row)==2*expected-1 and row[expected-1].strip().isdigit():
     normalized[ident]=row[:expected-1]+[''];other=row[expected-1:];other[0]=other[0].strip();normalized[int(other[0])]=other
   if normalized:
    shutil.copy2(target,clientbackup/name);after=patch(clienttext,normalized)
    with target.open('r+b') as f:f.write(after);f.truncate()
    clienttext=dec(after);mapping=rows(clienttext)
   original=dec(sftp.open(backup+'/'+name,'rb').read());remote=rows(original);remote_expected=int(original.split('|',1)[0])+1;assert remote_expected==expected
   allowed=set(rows(dec(sftp.open('/root/hxsy/Data/db/S_'+name[2:],'rb').read())))
   changes={};skipped=[]
   custom=set(range(61586,61597))|set(range(61600,61604))|set(range(180001,180020))
   if name=='T_EquipSet.ini':custom={1001,1002,1003}
   for ident,row in mapping.items():
    if ident not in allowed:continue
    if len(row)!=expected:
     if ident>10:skipped.append(ident)
     continue
    current=remote.get(ident)
    if current is None or ident in custom:changes[ident]=row;continue
    if len(current)!=expected:continue
    merged=current.copy()
    for i in range(1,expected-1):
     if (not merged[i].strip() or merged[i].strip().lower() in ['err','error','(null)']) and row[i].strip():merged[i]=row[i]
    if merged!=current:changes[ident]=merged
   after=patch(original,changes);sftp.open('/root/hxsy/Data/db/'+name,'wb').write(after)
   report[name]={'repaired':len(changes),'normalized_client_records':len(normalized),'skipped_malformed':skipped}
  titletext=rows(dec((CLIENT/'T_Title.ini').read_bytes()))
  restore=[i for i in json.loads((ROOT/'docs/sovereign-v2-final-manifest.json').read_text())['unused_title_ids'] if i in titletext and not titletext[i][1].startswith('Unused Title #')]
  restore_sql='BEGIN; '+''.join(f'INSERT INTO player_appellation(account_id,appellation_id) SELECT 2419,{i} WHERE NOT EXISTS(SELECT 1 FROM player_appellation WHERE account_id=2419 AND appellation_id={i});' for i in restore)+' COMMIT;'
  with sftp.open('/root/restore-valid-titles.sql','w') as f:f.write(restore_sql)
  report['valid_titles_restored']=len(restore)
 channel=ssh.get_transport().open_session();channel.set_combine_stderr(True);channel.exec_command('cd /tmp && runuser -u postgres -- psql -X -q -v ON_ERROR_STOP=1 -d FFDB1 < /root/restore-valid-titles.sql && systemctl start aurakingdom')
 result=b''
 while True:
  block=channel.recv(32768)
  if not block:break
  result+=block
 assert channel.recv_exit_status()==0,result.decode(errors='replace')
 (ROOT/'docs/server-text-schema-repair.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
finally:ssh.close()
