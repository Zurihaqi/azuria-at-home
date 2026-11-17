"""Sanitized tail of server disconnect diagnostics; no authentication records."""
from pathlib import Path
import re
for service in ('LoginServer','WorldServer','ZoneServer'):
    folder = Path('/root/hxsy', service)
    paths = []
    for pattern in ('Test*', 'System*'):
        paths += sorted(folder.glob(pattern), key=lambda p:p.stat().st_mtime)[-1:]
    print(service)
    for path in paths:
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-1500000))
            lines=stream.read().decode('utf8',errors='replace').splitlines()
        matches=[line[:250] for line in lines
            if re.search(r'time.?out|echo|disconnect|playerquit|gametime|kick|hack',line,re.I)
            and not re.search(r'pass|secret|credential|token|ticket|account_login',line,re.I)]
        print('\n'.join(matches[-10:]))
