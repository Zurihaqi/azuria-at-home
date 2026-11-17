"""Generate or synchronize the root .env file from local private/ credential files."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
priv = root / 'private'

net_file = priv / 'network-config.json'
net = json.loads(net_file.read_text()) if net_file.is_file() else {
    'server_vpn_ip': '100.64.0.10',
    'owner_vpn_ip': '100.64.0.1',
}

vm_pw_file = priv / 'vm-password.txt'
vm_pw = vm_pw_file.read_text().strip() if vm_pw_file.is_file() else ''

dash_login_file = priv / 'dashboard/LOGIN.txt'
dash_pw = ''
if dash_login_file.is_file():
    text = dash_login_file.read_text()
    if 'Password: ' in text:
        dash_pw = text.split('Password: ', 1)[1].splitlines()[0].strip()

acc_file = priv / 'game-accounts.json'
accounts = {}
if acc_file.is_file():
    raw = json.loads(acc_file.read_text())
    items = raw.get('accounts', raw) if isinstance(raw, dict) else raw
    if isinstance(items, list):
        for item in items:
            accounts[item['username']] = item['password']
    elif isinstance(items, dict):
        accounts = items

lines = [
    '# ============================================================================',
    '# Azuria at Home — Local Environment & Credentials (GIT-IGNORED)',
    '# Generated from private/ credential store via ops/sync-env.py',
    '# ============================================================================',
    '',
    '# --- Tailscale Mesh Network ---',
    f"AK_SERVER_IP={net.get('server_vpn_ip', '100.64.0.10')}",
    f"AK_OWNER_IP={net.get('owner_vpn_ip', '100.64.0.1')}",
    '',
    '# --- VirtualBox Guest SSH Administration ---',
    'AK_SSH_HOST=127.0.0.1',
    'AK_SSH_PORT=22222',
    'AK_SSH_USER=root',
    'AK_SSH_KEY_PATH=private/vm_ed25519',
    'AK_SSH_KNOWN_HOSTS=private/known_hosts',
    'AK_SSH_KEY_PASSPHRASE=""',
    f'AK_VM_ROOT_PASSWORD={vm_pw}',
    '',
    '# --- Astral Control Local Web Dashboard (http://127.0.0.1:8765) ---',
    'AK_DASHBOARD_URL=http://127.0.0.1:8765',
    'AK_DASHBOARD_USER=admin',
    f'AK_DASHBOARD_PASSWORD={dash_pw}',
    '',
    '# --- Game Accounts (FFMember / FFAccount) ---',
]

for username, password in accounts.items():
    prefix = f'AK_GAME_{username.upper()}'
    lines.append(f'{prefix}_USER={username}')
    lines.append(f'{prefix}_PASSWORD={password}')
    if username == 'playerone':
        lines.append(f'{prefix}_CHARACTER=Zrymund')
    lines.append('')

env_path = root / '.env'
env_path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
keys = [line.split('=', 1)[0] for line in lines if '=' in line and not line.startswith('#')]
print(f'Wrote {env_path.name} with {len(keys)} variables: {", ".join(keys)}')
