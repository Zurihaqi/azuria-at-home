from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'runtime'))
import paramiko
root=Path(__file__).resolve().parent.parent
name='20261024T141637Z'
destination=root/'private/backups'/name
destination.mkdir(parents=True,exist_ok=True)
client=paramiko.SSHClient()
client.load_host_keys(str(root/'private/known_hosts'))
key=paramiko.Ed25519Key.from_private_key_file(str(root/'private/vm_ed25519'),password='""')
client.connect('127.0.0.1',port=22222,username='root',pkey=key,look_for_keys=False,allow_agent=False)
try:
    with client.open_sftp() as sftp:
        for filename in ['FFAccount.dump','FFDB1.dump','FFMember.dump','globals.sql','server.tgz','SHA256SUMS','restore-report.json','COMPLETE']:
            sftp.get(f'/var/backups/aurakingdom/{name}/{filename}',str(destination/filename))
            print(f'Saved {filename}',flush=True)
finally:
    client.close()
