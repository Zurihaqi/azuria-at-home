from pathlib import Path
import sys
import shlex
import time
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
import paramiko

root = Path(__file__).resolve().parent.parent
client = paramiko.SSHClient()
client.load_host_keys(str(root / 'private/known_hosts'))
client.connect('127.0.0.1', port=22222, username='akadmin', password=(root / 'private/vm-password.txt').read_text().strip(), look_for_keys=False, allow_agent=False)
pub = (root / 'private/vm_ed25519.pub').read_text().strip()
command = 'mkdir -p /root/.ssh && chmod 700 /root/.ssh && printf "%s\\n" ' + shlex.quote(pub) + ' > /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys && echo SSH_KEY_INSTALLED'
channel = client.get_transport().open_session()
channel.get_pty()
channel.exec_command('su - root -c ' + shlex.quote(command))
received = b''
deadline = time.monotonic() + 15
while b'Password:' not in received:
    if time.monotonic() > deadline:
        raise RuntimeError('No password prompt from su')
    if channel.recv_ready():
        received += channel.recv(4096)
    time.sleep(.1)
channel.send((root / 'private/vm-password.txt').read_text().strip() + '\n')
result = b''
while not channel.exit_status_ready() or channel.recv_ready():
    if channel.recv_ready():
        result += channel.recv(4096)
    time.sleep(.1)
if channel.recv_exit_status() != 0 or b'SSH_KEY_INSTALLED' not in result:
    raise RuntimeError('SSH key recovery failed')
print('SSH key installed successfully')
client.close()
