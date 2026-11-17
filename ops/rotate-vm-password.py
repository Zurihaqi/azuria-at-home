from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
import paramiko

root = Path(__file__).resolve().parent.parent
client = paramiko.SSHClient()
client.load_host_keys(str(root / 'private/known_hosts'))
key = paramiko.Ed25519Key.from_private_key_file(str(root / 'private/vm_ed25519'), password='""')
client.connect('127.0.0.1', port=22222, username='root', pkey=key, look_for_keys=False, allow_agent=False)
password = secrets.token_hex(24)
stdin, stdout, stderr = client.exec_command('chpasswd')
stdin.write(f'root:{password}\nakadmin:{password}\n')
stdin.channel.shutdown_write()
error = stderr.read()
if stdout.channel.recv_exit_status() != 0:
    raise RuntimeError('Guest password rotation failed')
(root / 'private/vm-password.txt').write_text(password)
client.close()
print('Guest passwords rotated; stored only in protected private/vm-password.txt')
