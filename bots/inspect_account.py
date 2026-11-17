import subprocess
from lab import assert_inside
assert_inside()
subprocess.run(['runuser', '-u', 'postgres', '--', '/usr/lib/postgresql/13/bin/psql',
    '-h', '/run/postgresql', '-X', '-At', '-d', 'FFMember', '-c',
    "SELECT prosrc FROM pg_proc WHERE proname='account_login'"], check=True, cwd='/')
