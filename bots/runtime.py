"""Explicitly configured normal-world identity; lab remains the default."""
import json
import os
from pathlib import Path
import sys

NORMAL_WORLD = '--normal-world' in sys.argv
PROFILE = sys.argv[sys.argv.index('--profile')+1] if '--profile' in sys.argv else 'awan'
if PROFILE not in ('awan','arden'):
    raise RuntimeError('Unknown bot profile')
STATE = Path('/var/lib/ak-bots/arden' if PROFILE == 'arden' else '/var/lib/ak-bots/pilot') if NORMAL_WORLD else Path('/run/pilot')
CONFIG = Path('/etc/ak-bots/arden-world.json' if PROFILE == 'arden' else '/etc/ak-bots/normal-world.json')


def server_ip():
    if os.environ.get('AK_SERVER_IP'):
        return os.environ['AK_SERVER_IP']
    conf = Path('/etc/ak-server.conf')
    if conf.is_file():
        for line in conf.read_text().splitlines():
            if line.startswith('AK_SERVER_IP='):
                return line.split('=', 1)[1].strip().strip('"\'')
    env_file = Path(__file__).resolve().parent.parent / '.env'
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.startswith('AK_SERVER_IP='):
                return line.split('=', 1)[1].strip().strip('"\'')
    local_cfg = Path(__file__).resolve().parent.parent / 'private/network-config.json'
    if local_cfg.is_file():
        return json.loads(local_cfg.read_text()).get('server_vpn_ip', '100.64.0.10')
    return '100.64.0.10'


def normal_config():
    st = CONFIG.stat()
    if st.st_uid != 0 or st.st_mode & 0o022:
        raise RuntimeError('Normal-world authorization must be root-owned and not writable by the bot')
    config = json.loads(CONFIG.read_text())
    if config.get('enabled') is not True or config.get('username') != ('ardenbot' if PROFILE == 'arden' else 'awanbot'):
        raise RuntimeError('Normal-world bot is disabled or has an unexpected identity')
    return config
