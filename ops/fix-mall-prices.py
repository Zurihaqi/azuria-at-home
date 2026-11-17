"""Guest-side price correction; run only after players have logged out."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

def sql(statement):
    result = subprocess.run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-q', '-tA',
                             '-v', 'ON_ERROR_STOP=1', '-d', 'FFAccount'], input=statement,
                            text=True, capture_output=True, cwd='/tmp', check=True)
    return result.stdout.strip()

backup = Path('/var/backups/aurakingdom') / ('pre-mall-price-fix-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
with (backup / 'catalog.csv').open('w') as output:
    subprocess.run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-q', '-d', 'FFAccount',
                    '-c', "COPY (SELECT * FROM itemmall WHERE note LIKE 'codex:gear-catalog:%') TO STDOUT WITH CSV HEADER"],
                   stdout=output, cwd='/tmp', check=True)
subprocess.run(['systemctl', 'stop', 'aurakingdom'], check=True)
try:
    print(sql("UPDATE itemmall SET point=1,special_price=0 WHERE note IN ('codex:gear-catalog:v1','codex:gear-catalog:probe'); SELECT count(*) FROM itemmall WHERE note LIKE 'codex:gear-catalog:%' AND point=1 AND special_price=0;"))
finally:
    subprocess.run(['systemctl', 'start', 'aurakingdom'], check=True)
print('Backup:', backup)
