"""Sanitized sandbox diagnostics (native logs sometimes contain DB passwords)."""
from pathlib import Path
import re
import sys
from lab import assert_inside
offline = '--offline' in sys.argv
if not offline:
    assert_inside()
game = Path('/var/lib/ak-bot-lab/game') if offline else Path('/root/hxsy')
for service in ('TicketServer', 'GatewayServer', 'LoginServer', 'WorldServer', 'MissionServer', 'ZoneServer'):
    files = sorted((game / service).glob('Test*'), key=lambda p: p.stat().st_mtime)[-1:]
    files += [Path('/var/lib/ak-bot-lab/logs', service + '.log')]
    print(service)
    lines = []
    for file in files:
        if file.is_file():
            for line in file.read_text(errors='replace').splitlines():
                if re.search(r'pass(word|wd)?|secret|key=|account_login\(', line, re.I):
                    continue
                if re.search(r'fail|error|connect|server.*(id|port|state)|database|assert', line, re.I):
                    lines.append(line[:250])
    print('\n'.join(lines[-12:]))
