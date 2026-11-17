"""Workspace-local SSH/SFTP helper; keeps the administration key encrypted on disk."""
from pathlib import Path
import argparse
import os
import sys
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
import paramiko

root = Path(__file__).resolve().parent.parent
env_file = root / '.env'
if env_file.is_file():
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['run', 'put', 'get'])
parser.add_argument('source')
parser.add_argument('destination', nargs='?')
args = parser.parse_args()
client = paramiko.SSHClient()
client.load_host_keys(str(root / os.environ.get('AK_SSH_KNOWN_HOSTS', 'private/known_hosts')))
key = paramiko.Ed25519Key.from_private_key_file(
    str(root / os.environ.get('AK_SSH_KEY_PATH', 'private/vm_ed25519')),
    password=os.environ.get('AK_SSH_KEY_PASSPHRASE', '""'),
)
client.connect(
    os.environ.get('AK_SSH_HOST', '127.0.0.1'),
    port=int(os.environ.get('AK_SSH_PORT', '22222')),
    username=os.environ.get('AK_SSH_USER', 'root'),
    pkey=key,
    look_for_keys=False,
    allow_agent=False,
    timeout=10,
)
try:
    if args.action == 'run':
        channel = client.get_transport().open_session()
        channel.set_combine_stderr(True)
        channel.exec_command(args.source)
        while True:
            data = channel.recv(32768)
            if not data:
                break
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        sys.exit(channel.recv_exit_status())
    else:
        if not args.destination:
            parser.error('A destination is required for file transfers')
        with client.open_sftp() as sftp:
            if args.action == 'put':
                sftp.put(args.source, args.destination)
            else:
                sftp.get(args.source, args.destination)
        print('Transfer complete')
finally:
    client.close()
