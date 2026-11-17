"""Root-only, offline-network protocol lab. Never starts production services.

Copy to /opt/ak-bot-prototype/lab.py in the VM. Auth-only by design until the
ordinary-player feasibility gate has passed. No production account writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import subprocess as sp
import sys
import time

BASE = Path('/var/lib/ak-bot-lab')
GAME = BASE / 'game'
PG = '/usr/lib/postgresql/13/bin/'
DBS = ('FFAccount', 'FFDB1', 'FFMember')
UNIT = 'ak-bot-lab'


def run(args, **kwargs):
    return sp.run([str(a) for a in args], check=True, **kwargs)


def postgres(args, **kwargs):
    return run(['runuser', '-u', 'postgres', '--', *args], **kwargs)


def marker():
    return BASE / 'run' / 'ak-bot-lab.json'


def assert_inside():
    info = json.loads(Path('/run/ak-bot-lab.json').read_text())
    if info['netns'] != os.readlink('/proc/self/ns/net'):
        raise RuntimeError('Not in lab network namespace')
    if Path('/run/ak-bot-lab.json').stat().st_ino != marker().stat().st_ino:
        raise RuntimeError('Private /run mount missing')
    if not Path('/root/hxsy/.ak-bot-lab').exists():
        raise RuntimeError('Private game mount missing')
    links = json.loads(sp.check_output(['ip', '-j', 'link', 'show']))
    if {link['ifname'] for link in links} != {'lo'}:
        raise RuntimeError('Lab must have loopback ONLY')
    return info


def prepare():
    if (BASE / 'manifest.json').exists() or (BASE / 'pgdata').exists():
        raise RuntimeError('Prepared lab already exists; refusing overwrite')
    BASE.mkdir(mode=0o750, exist_ok=True)
    os.chown(BASE, 0, pwd.getpwnam('postgres').pw_gid)
    for name in ('snapshots', 'run', 'tmp', 'logs'):
        (BASE / name).mkdir(mode=0o700, exist_ok=True)
    # PostgreSQL needs access to its socket parent. Everything remains local.
    (BASE / 'run').chmod(0o755)
    (BASE / 'tmp').chmod(0o1777)
    GAME.mkdir(mode=0o700, exist_ok=True)
    manifest = {}
    source = Path('/root/hxsy')
    for name in ('setup.ini', 'config.ini', 'config09.ini'):
        if (source / name).is_file():
            shutil.copy2(source / name, GAME / name)
    shutil.copytree(source / 'Data', GAME / 'Data', dirs_exist_ok=True)
    for name in ('TicketServer', 'GatewayServer', 'LoginServer',
                 'MissionServer', 'WorldServer', 'ZoneServer'):
        target = GAME / name
        target.mkdir(exist_ok=True)
        for filename in (name, 'setup.ini'):
            src = source / name / filename
            if not src.is_file() and filename == 'setup.ini':
                continue
            shutil.copy2(src, target / filename)
            manifest[f'{name}/{filename}'] = hashlib.sha256(src.read_bytes()).hexdigest()
    (GAME / 'Logs').mkdir(exist_ok=True)
    (GAME / '.ak-bot-lab').write_text('isolated copy\n')
    # Explicit host socket: these operations only read production.
    with (BASE / 'snapshots/roles.sql').open('wb') as out:
        postgres([PG + 'pg_dumpall', '-h', '/var/run/postgresql', '--roles-only'], stdout=out)
    for db in DBS:
        with (BASE / 'snapshots' / (db + '.dump')).open('wb') as out:
            postgres([PG + 'pg_dump', '-h', '/var/run/postgresql', '-Fc', db], stdout=out)
    (BASE / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('Prepared copied binaries, tables and read-only database snapshots.')


def init():
    # Must only be invoked as PID 1 of a fresh unshare --pid --net --mount.
    if os.getpid() != 1 or os.readlink('/proc/self/ns/net') == os.environ.get('AK_LAB_HOST_NETNS'):
        raise RuntimeError('Namespace init requires PID 1')
    run(['mount', '--make-rprivate', '/'])
    run(['ip', 'link', 'set', 'lo', 'up'])
    lab_ip = os.environ.get('AK_SERVER_IP', '100.64.0.10')
    if Path('/etc/ak-server.conf').is_file():
        for line in Path('/etc/ak-server.conf').read_text().splitlines():
            if line.startswith('AK_SERVER_IP='):
                lab_ip = line.split('=', 1)[1].strip().strip('"\'')
    run(['ip', 'addr', 'add', f'{lab_ip}/32', 'dev', 'lo'])
    run(['mount', '--bind', GAME, '/root/hxsy'])
    run(['mount', '--bind', BASE / 'run', '/run'])
    run(['mount', '--bind', BASE / 'tmp', '/tmp'])
    full = os.environ.get('AK_LAB_FULL') == '1'
    info = {'netns': os.readlink('/proc/self/ns/net'), 'pidns': os.readlink('/proc/self/ns/pid'),
            'created': time.time(), 'mode': 'full-isolated' if full else 'authentication-only'}
    Path('/run/ak-bot-lab.json').write_text(json.dumps(info))
    assert_inside()
    data = BASE / 'pgdata'
    socket = Path('/run/postgresql')
    socket.mkdir(exist_ok=True)
    os.chown(socket, pwd.getpwnam('postgres').pw_uid, pwd.getpwnam('postgres').pw_gid)
    if not data.exists():
        data.mkdir(mode=0o700)
        os.chown(data, pwd.getpwnam('postgres').pw_uid, pwd.getpwnam('postgres').pw_gid)
        postgres([PG + 'initdb', '-D', data, '--auth-local=trust', '--auth-host=reject'], stdout=sp.DEVNULL)
        with (data / 'postgresql.conf').open('a') as f:
            f.write("\nlisten_addresses='127.0.0.1'\nshared_buffers='32MB'\nmax_connections=35\n")
    # Only this network namespace can access its loopback; native services use TCP.
    (data / 'pg_hba.conf').write_text('local all all trust\nhost all all 127.0.0.1/32 trust\n')
    postgres([PG + 'pg_ctl', '-D', data, '-l', data / 'lab.log', '-w', 'start'], stdout=sp.DEVNULL)
    if not (BASE / 'restored').exists():
        roles = (BASE / 'snapshots/roles.sql').read_text()
        roles = '\n'.join(line for line in roles.splitlines() if line != 'CREATE ROLE postgres;')
        postgres([PG + 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-d', 'postgres'],
                 input=roles.encode(), stdout=sp.DEVNULL)
        for db in DBS:
            postgres([PG + 'createdb', db])
            with (BASE / 'snapshots' / (db + '.dump')).open('rb') as src:
                postgres([PG + 'pg_restore', '--exit-on-error', '-d', db], stdin=src, stdout=sp.DEVNULL)
        (BASE / 'restored').touch()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    children = []
    services = [('TicketServer', ['-p', '7777']), ('GatewayServer', []), ('LoginServer', [])]
    if full:
        services += [('MissionServer', []), ('WorldServer', []), ('ZoneServer', [])]
    for name, args in services:
        handle = (BASE / 'logs' / (name + '.log')).open('ab', buffering=0)
        children.append(sp.Popen(['./' + name, *args], cwd='/root/hxsy/' + name,
                                 env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C'}, stdout=handle, stderr=handle))
        port = {'TicketServer': 7777, 'GatewayServer': 5560, 'LoginServer': 6543,
                'MissionServer': 7654, 'WorldServer': 5568, 'ZoneServer': 10020}[name]
        # ZoneServer exits when WorldServer is not listening yet. Table loading
        # takes a variable amount of time; a fixed delay is not a readiness test.
        for _ in range(240):
            if children[-1].poll() is not None:
                raise RuntimeError(name + ' exited during startup: ' + str(children[-1].returncode))
            listeners = [line.split() for line in Path('/proc/net/tcp').read_text().splitlines()[1:]]
            if any(row[3] == '0A' and int(row[1].split(':')[1], 16) == port for row in listeners):
                break
            time.sleep(.25)
        else:
            raise RuntimeError(name + ' did not become ready within 60 seconds')
    print('Lab auth services ready; no route to production.', flush=True)
    extra = {name for name, _ in services[3:]}
    relay = None
    while not stopping:
        if full and Path('/run/enable-observer').exists() and relay is None:
            relay_log = (BASE / 'logs/observer-relay.log').open('ab', buffering=0)
            relay = sp.Popen([sys.executable, '/opt/ak-bot-prototype/relay.py', 'inside'],
                             stdout=relay_log, stderr=relay_log)
        if full and time.time() - (BASE / 'lease').stat().st_mtime > 900:
            print('Lab lease expired; restoring production through unit cleanup.', flush=True)
            break
        for flag, name in (('enable-world', 'WorldServer'), ('enable-mission', 'MissionServer')):
            if Path('/run', flag).exists() and name not in extra:
                handle = (BASE / 'logs' / (name + '.log')).open('ab', buffering=0)
                children.append(sp.Popen(['./' + name], cwd='/root/hxsy/' + name,
                                         env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C'}, stdout=handle, stderr=handle))
                extra.add(name)
                print('Lab ' + name + ' starting (no ZoneServer).', flush=True)
        if any(p.poll() is not None for p in children):
            print('Lab service exits: ' + str([(p.args[0], p.returncode) for p in children if p.poll() is not None]), flush=True)
            break
        time.sleep(1)
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
    if relay is not None:
        relay.terminate()
        relay.wait(timeout=8)
    for child in children:
        try:
            child.wait(timeout=8)
        except sp.TimeoutExpired:
            child.kill()
    postgres([PG + 'pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop'], stdout=sp.DEVNULL)


def enter(command):
    parent = int(sp.check_output(['systemctl', 'show', UNIT, '-p', 'MainPID', '--value']))
    if parent <= 1:
        raise RuntimeError('Lab is not running')
    (BASE / 'lease').touch()
    candidates = [parent]
    candidates += [int(x) for x in Path(f'/proc/{parent}/task/{parent}/children').read_text().split()]
    hostnet = os.readlink('/proc/self/ns/net')
    hostpid = os.readlink('/proc/self/ns/pid')
    for pid in candidates:
        if os.readlink(f'/proc/{pid}/ns/net') != hostnet and os.readlink(f'/proc/{pid}/ns/pid') != hostpid:
            os.execvp('nsenter', ['nsenter', '-t', str(pid), '-m', '-n', '-p', '--',
                                 sys.executable, __file__, 'checked', *command])
    raise RuntimeError('Isolated namespace PID not found')


if __name__ == '__main__':
    if os.geteuid() != 0:
        sys.exit('Root required to manage namespaces; player client will be unprivileged.')
    action = sys.argv[1]
    if action == 'prepare':
        prepare()
    elif action in ('start', 'start-full'):
        full = action == 'start-full'
        if full and sp.run(['systemctl', 'is-active', '--quiet', 'aurakingdom']).returncode == 0:
            sys.exit('Stop production game services before starting a full lab.')
        if full:
            (BASE / 'lease').touch()
        sp.run(['systemctl', 'reset-failed', UNIT], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        properties = ['--property=MemoryMax=3600M', '--setenv=AK_LAB_FULL=1',
                      '--property=ExecStopPost=/usr/bin/python3 /opt/ak-bot-prototype/restore_production.py'] if full else ['--property=MemoryMax=850M']
        run(['systemd-run', '--collect', '--unit=' + UNIT, *properties,
             '--property=MemorySwapMax=' + ('850M' if full else '0'), '--property=TasksMax=160',
             '--setenv=AK_LAB_HOST_NETNS=' + os.readlink('/proc/self/ns/net'),
             'unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', '--mount-proc',
             sys.executable, str(Path(__file__).resolve()), 'init'])
    elif action == 'init':
        init()
    elif action == 'enter':
        enter(sys.argv[2:])
    elif action == 'checked':
        assert_inside()
        os.execvp(sys.argv[2], sys.argv[2:])
    elif action == 'stop':
        # Signal namespace init so it can terminate services and PostgreSQL first.
        run([sys.executable, __file__, 'enter', 'kill', '-TERM', '1'])
    else:
        sys.exit('Use prepare/start/enter/stop')
