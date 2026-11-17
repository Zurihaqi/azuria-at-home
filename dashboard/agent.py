"""Fixed, allowlisted guest operations. Request JSON arrives over encrypted SSH stdin."""
import contextlib
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'Expected a whole number from {low} to {high}')
    return value


def quote(value):
    if not isinstance(value, str) or len(value) > 200 or '\x00' in value:
        raise ValueError('Invalid text')
    return "'" + value.replace("'", "''") + "'"


def command(args, timeout=180):
    r = subprocess.run(args, text=True, capture_output=True, cwd='/tmp', timeout=timeout)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout or 'Command failed')[-1200:])
    return r.stdout.strip()


def sql(db, statement):
    r = subprocess.run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-q', '-tA',
                        '-v', 'ON_ERROR_STOP=1', '-d', db], input=statement, text=True,
                       capture_output=True, cwd='/tmp', timeout=180)
    if r.returncode:
        raise RuntimeError(r.stderr[-1500:])
    return r.stdout.strip()


def rows(db, query):
    return json.loads(sql(db, f"SELECT coalesce(json_agg(t),'[]') FROM ({query}) t;"))


def active():
    return subprocess.run(['systemctl', 'is-active', '--quiet', 'aurakingdom']).returncode == 0


def online():
    return rows('FFDB1', 'SELECT id,given_name FROM player_characters WHERE quit=0 ORDER BY id')


def backup(databases):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    directory = Path('/var/backups/aurakingdom') / ('dashboard-' + stamp)
    directory.mkdir(mode=0o700)
    for db in databases:
        with (directory / (db + '.dump')).open('wb') as out:
            r = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', db],
                               stdout=out, stderr=subprocess.PIPE, cwd='/tmp', timeout=300)
            if r.returncode:
                raise RuntimeError('Database backup failed; edit was not applied')
    return str(directory)


@contextlib.contextmanager
def edit(databases):
    players = online()
    if players:
        raise ValueError('Log everyone out first: ' + ', '.join(p['given_name'] for p in players))
    running = active()
    if running:
        command(['systemctl', 'stop', 'aurakingdom'])
    try:
        # Recheck after shutdown, before any database write.
        if online():
            raise ValueError('A character connected during the check. Log everyone out and retry.')
        location = backup(databases)
        yield location
    finally:
        if running:
            command(['systemctl', 'start', 'aurakingdom'])


def key_where(key):
    columns = ['item_group', 'detail_type', 'item_index', 'money_unit']
    return ' AND '.join(f'{c}={integer(key[c], 0, 32767)}' for c in columns)


BOT_BASE = Path('/var/lib/ak-bot-lab')


def bot_json(path, max_bytes=65536):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        return {}
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def bot_tail(path):
    if path.is_symlink() or not path.is_file():
        return []
    with path.open('rb') as stream:
        size = stream.seek(0, 2)
        stream.seek(max(0, size - 262144))
        if size > 262144:
            stream.readline()
        lines = stream.read(262144).decode('utf-8', errors='replace').splitlines()[-500:]
    result = []
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                result.append(value)
        except ValueError:
            continue
    return result


def bot_text(value, limit=300):
    if not isinstance(value, str):
        return ''
    # Never expose arbitrary native logs, authentication values or session material.
    if re.search(r'pass(?:word|wd|phrase)?|secret|ticket|token|credential|private.?key|hash|[a-f0-9]{32,}', value, re.I):
        return '[sensitive message omitted]'
    return ''.join(c for c in value if c >= ' ' or c in '\n\t')[:limit]


def bot_number(value):
    return value if type(value) in (int, float) and -1e12 < value < 1e12 else None


def bot_position(public, normal, profile, fresh, observations=()):
    position = public.get('position')
    if isinstance(position, dict):
        x, y = bot_number(position.get('x')), bot_number(position.get('y'))
        observed = bot_number(position.get('observed_at'))
        node = bot_number(position.get('map'))
        if (x is not None and y is not None and node == public.get('map') and
                observed is not None and 0 <= time.time() - observed < 86400):
            return dict(x=round(x, 1), y=round(y, 1), map=node, observed_at=observed,
                        source='native', stale=not fresh or time.time() - observed > 30)
    for row in observations:  # Newest first, bounded by the existing log reader.
        message = row.get('message', '')
        if message.startswith(('Native respawn confirmed', 'Pilot died;', 'Bot session started')):
            break
        point = re.fullmatch(r'Native movement endpoint confirmed at \((-?[0-9.]+), (-?[0-9.]+)\)', message)
        correction = re.match(r'Native movement correction: position=\((-?[0-9.]+),(-?[0-9.]+)\)', message)
        if point or correction:
            try:
                x, y = map(float, (point or correction).groups())
            except ValueError:
                continue
            observed = bot_number(row.get('time'))
            if (bot_number(x) is not None and bot_number(y) is not None and observed is not None
                    and 0 <= time.time() - observed < 86400):
                return dict(x=round(x, 1), y=round(y, 1), map=public.get('map'), source='native',
                            observed_at=observed, stale=not fresh or time.time() - observed > 30)
        if message.startswith('Native map entry:'):
            break  # Never reuse a coordinate from the previous map.
    if normal:
        # Fixed bot IDs only; never interpolate a public-file/request identity.
        ident = 50000003 if profile == 'arden' else 50000002
        try:
            saved = rows('FFDB1', f'SELECT node_id,x,y FROM player_characters WHERE id={ident}')
            if saved and (public.get('map') is None or saved[0].get('node_id') == public.get('map')):
                x, y = bot_number(saved[0].get('x')), bot_number(saved[0].get('y'))
                if x is not None and y is not None:
                    return dict(x=round(x, 1), y=round(y, 1), map=saved[0].get('node_id'),
                                source='saved', observed_at=None, stale=True)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            pass
    return None


def bot_process_running(profile='awan'):
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = path.read_bytes().split(b'\0')
            script_index = 1
            while script_index < len(args) and args[script_index] in (b'-u', b'-B'):
                script_index += 1
            if len(args) > script_index and args[script_index] == b'/opt/ak-bot-prototype/probe_login.py' and Path(os.fsdecode(args[0])).name in ('python3', 'python'):
                options = args[script_index+1:]
                selected = options[options.index(b'--profile')+1] if b'--profile' in options else b'awan'
                if selected == profile.encode():
                    return True
        except (OSError, ValueError):
            continue
    return False


def _bots_status(limit, profile='awan'):
    limit = integer(limit, 1, 500)
    lab_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'ak-bot-lab'], capture_output=True).returncode == 0
    normal = bot_json(Path('/etc/ak-bots/arden-world.json' if profile=='arden' else '/etc/ak-bots/normal-world.json')).get('enabled') is True
    state_dir = Path('/var/lib/ak-bots/arden' if profile=='arden' else '/var/lib/ak-bots/pilot') if normal else BOT_BASE / 'run/pilot'
    process_running = (normal or lab_active) and bot_process_running(profile)
    public = bot_json(state_dir / 'status-public.json')
    observation = bot_json(state_dir / 'last-observation.json')
    identity = bot_json(state_dir / 'character.json')
    model = bot_json(state_dir / 'encounter-model.json', max_bytes=2000000)
    if model.get('version') != 1 or model.get('method') != 'contextual-nearest-neighbours':
        model = {}
    updated = bot_number(public.get('updated_at'))
    fresh = updated is not None and 0 <= time.time() - updated < 15
    phase = public.get('phase') if public.get('phase') in ('connecting', 'online', 'paused', 'stopped', 'failed') else 'stopped'
    runtime = phase if process_running and fresh else 'stale' if process_running else 'stopped'
    logs = []
    # Older test sessions have sanitized input metadata, not a structured bot log.
    for row in ([] if normal else bot_tail(BOT_BASE / 'logs/client-gameplay.jsonl')):
        opcode, fields = row.get('opcode'), row.get('fields')
        message = None
        if opcode == 2 and isinstance(fields, list) and len(fields) == 3 and all(type(x) is int for x in fields):
            verb = {1:'Accept quest', 2:'Claim quest reward', 5:'Abandon quest', 9:'Open starter quest'}.get(fields[0], 'Quest operation')
            message = f'{verb}: {fields[1]} (recorded input; result not implied)'
        elif opcode == 68 and isinstance(fields, list) and len(fields) == 6 and all(type(x) is int for x in fields):
            message = f'Equipment request: slot {fields[1]} → slot {fields[4]} (recorded input)'
        elif row.get('movement_failure') in ('movement_state_guard', 'no_move_state'):
            message = 'Native movement guard: ' + row['movement_failure']
        if message:
            logs.append({'time': bot_number(row.get('time')), 'level':'info', 'source':'recorded input', 'message':message, 'bot':'Lab session'})
    for row in bot_tail(state_dir / 'events-public.jsonl'):
        level = row.get('level') if row.get('level') in ('info', 'warning', 'error') else 'info'
        logs.append({'time':bot_number(row.get('time')), 'level':level, 'source':'bot',
                     'message':bot_text(row.get('message')), 'bot':bot_text(row.get('bot'), 40)})
    previous_route_incomplete = observation.get('moved') is False and observation.get('quitting') is False
    if not public and previous_route_incomplete:
        logs.append({'time':bot_number(observation.get('time')), 'level':'warning',
                     'source':'last probe snapshot', 'bot':bot_text(identity.get('name') or 'Pilot',40),
                     'message':'Previous probe ended without a confirmed route endpoint or normal logout. Exact error text was not recorded in this older snapshot.'})
    logs.sort(key=lambda row: row['time'] or 0, reverse=True)
    bot = {'name':bot_text(public.get('name') or identity.get('name') or 'Pilot',40),
           'profile':profile,
           'character_id':bot_number(public.get('character_id') or identity.get('id')),
           'level':bot_number(public.get('level')), 'map':bot_number(public.get('map') or observation.get('map')),
           'position':bot_position(public, normal, profile, fresh, logs),
           'quest':bot_number(public.get('quest')), 'runtime':runtime,
           'learning':{'status':bot_text(public.get('learning') or 'disabled',40),
                       'labels':bot_number(public.get('learning_labels')),
                       'model':('evaluated-shadow' if model.get('approved') is True else 'not-ready') if model else bot_text(public.get('learning_model') or 'untrained',40),
                       'reason':bot_text(model.get('reason') or public.get('learning_train_reason') or '',180)},
           'task':bot_text(public.get('task') or 'No test bot is running'),
           'last_failure':bot_text(public.get('last_failure')) or ('Previous probe did not confirm its route endpoint; exact error was not recorded.' if not public and previous_route_incomplete else ''),
           'last_outcome':phase if updated else 'not recorded',
           'updated_at':updated or bot_number(observation.get('time'))}
    if not process_running:
        bot['task'] = 'Stopped — last known state shown below'
    return {'mode':'prototype', 'production_enabled':normal, 'world':'normal' if normal else 'isolated', 'lab_active':lab_active,
            'runtime':runtime, 'online':1 if runtime in ('online','paused') else 0, 'bots':[bot],
            'logs':logs[:limit], 'checked_at':time.time(), 'history_only':not process_running}


def bots_status(limit):
    result = _bots_status(limit)
    if bot_json(Path('/etc/ak-bots/arden-world.json')).get('enabled') is True:
        arden = _bots_status(limit, 'arden')
        result['bots'] += arden['bots']
        result['online'] += arden['online']
        result['logs'] = sorted(result['logs'] + arden['logs'], key=lambda row:row['time'] or 0, reverse=True)[:integer(limit,1,500)]
        result['history_only'] = result['history_only'] and arden['history_only']
        if result['online']:
            result['runtime'] = 'online'
    return result


def bot_control(req):
    """Start or stop a prototype bot via the fixed root-owned control script."""
    operation, profile = req.get('operation'), req.get('profile', 'awan')
    if operation not in ('start', 'stop'):
        raise ValueError('Unknown bot operation')
    if profile not in ('awan', 'arden'):
        raise ValueError('Unknown bot profile')
    if operation == 'start':
        world = Path(f'/etc/ak-bots/{profile}-world.json' if profile == 'arden'
                     else '/etc/ak-bots/normal-world.json')
        if bot_json(world).get('enabled') is not True:
            raise ValueError(f'Normal-world bot access is not enabled for {profile}')
        if not active():
            raise ValueError('The game service is not active. Start the realm first.')
    result = command(['python3', '/opt/ak-bot-prototype/bot_control.py', operation, profile],
                     timeout=180)
    payload = json.loads(result)
    if payload.get('error'):
        raise ValueError(payload['error'])
    return {'message': payload.get('message', 'Done')}


def run(req):
    action = req.get('action')
    if action == 'bots':
        return bots_status(req.get('limit', 200))
    if action == 'bot_control':
        return bot_control(req)
    if action == 'status':
        services = []
        for name in ['TicketServer', 'GatewayServer', 'LoginServer', 'MissionServer', 'WorldServer', 'ZoneServer']:
            p = subprocess.run(['pgrep', '-x', name], text=True, capture_output=True)
            services.append({'name': name, 'running': p.returncode == 0, 'pids': p.stdout.split()})
        counts = rows('FFDB1', 'SELECT count(*) AS characters,count(*) FILTER (WHERE quit=0) AS online FROM player_characters')[0]
        vpn_ip = os.environ.get('AK_SERVER_IP', '100.64.0.10')
        if Path('/etc/ak-server.conf').is_file():
            for line in Path('/etc/ak-server.conf').read_text().splitlines():
                if line.startswith('AK_SERVER_IP='):
                    vpn_ip = line.split('=', 1)[1].strip().strip('"\'')
        return {'active': active(), 'services': services, **counts,
                'accounts': int(sql('FFAccount', 'SELECT count(*) FROM accounts;')),
                'mall_items': int(sql('FFAccount', 'SELECT count(*) FROM itemmall;')),
                'disk': command(['df', '-h', '/']), 'vpn_ip': vpn_ip}
    if action == 'players':
        search = quote('%' + str(req.get('search', ''))[:80] + '%')
        return rows('FFDB1', f'''SELECT id,given_name,account_id,account_name,level,gold,bind_gold,
            skill_point,privilege,quit,node_id FROM player_characters
            WHERE given_name ILIKE {search} OR account_name ILIKE {search} ORDER BY id LIMIT 300''')
    if action == 'accounts':
        return rows('FFAccount', 'SELECT id,username,state FROM accounts ORDER BY id DESC LIMIT 300')
    if action == 'mall':
        page = integer(req.get('page', 1), 1, 100000)
        conditions = []
        if req.get('category') not in [None, '']:
            conditions += ['item_group=6', f"detail_type={integer(req['category'], 1, 44)}", 'money_unit=1']
        if req.get('item_id') not in [None, '']:
            conditions.append(f"item_id={integer(req['item_id'], 1, 65535)}")
        if 'item_ids' in req:
            ids = req['item_ids']
            if not isinstance(ids,list) or len(ids)>65535:
                raise ValueError('Invalid item search')
            ids = [integer(i,1,65535) for i in ids]
            conditions.append('item_id IN (' + ','.join(map(str,ids)) + ')' if ids else 'false')
        where = ' AND '.join(conditions) or 'true'
        count = int(sql('FFAccount', f'SELECT count(*) FROM itemmall WHERE {where};'))
        data = rows('FFAccount', f'''SELECT item_id,item_group,detail_type,item_index,item_num,money_unit,
            point,special_price,sell,level_limit FROM itemmall WHERE {where}
            ORDER BY item_group,detail_type,item_index,money_unit LIMIT 40 OFFSET {(page-1)*40}''')
        return {'total': count, 'page': page, 'items': data}
    if action == 'logs':
        return {'text': command(['journalctl', '-u', 'aurakingdom', '-n', '100', '--reverse', '--no-pager', '-o', 'short-iso'])}
    if action == 'backups':
        base = Path('/var/backups/aurakingdom')
        return [{'name': p.name, 'path': str(p), 'bytes': sum(x.stat().st_size for x in p.glob('*.dump'))}
                for p in sorted(base.iterdir(), reverse=True)[:30] if p.is_dir()]
    if action == 'backup':
        # Online pg_dump is transactionally consistent per database. Scheduled edits use offline backups.
        return {'backup': backup(['FFAccount', 'FFDB1', 'FFMember']), 'message': 'Three database snapshots saved'}
    if action == 'service':
        operation = req.get('operation')
        if operation not in ['start', 'stop', 'restart']:
            raise ValueError('Unknown service operation')
        if operation != 'start' and online():
            raise ValueError('Players are online. Log everyone out before stopping or restarting.')
        command(['systemctl', operation, 'aurakingdom'])
        return {'active': active(), 'message': f'Service {operation} requested. Channel startup can take a minute.'}
    if action == 'player_edit':
        player = integer(req.get('id'), 1, 2147483647)
        data = req.get('values', {})
        limits = {'gold': (0, 2000000), 'bind_gold': (0, 2000000), 'level': (1, 99),
                  'skill_point': (0, 1000), 'privilege': (0, 5)}
        if not data or set(data) - limits.keys():
            raise ValueError('Unsupported character field')
        setters = ','.join(f'{k}={integer(v,*limits[k])}' for k,v in data.items())
        if not rows('FFDB1', f'SELECT id FROM player_characters WHERE id={player}'):
            raise ValueError('Character not found')
        with edit(['FFDB1']) as location:
            sql('FFDB1', f'BEGIN; UPDATE player_characters SET {setters} WHERE id={player}; COMMIT;')
        return {'backup': location, 'message': 'Character saved; quest records were not modified'}
    if action == 'account_create':
        name, password = req.get('username', ''), req.get('password', '')
        if not re.fullmatch('[a-zA-Z0-9_]{3,24}', name):
            raise ValueError('Username: 3–24 letters, digits or underscores')
        if not re.fullmatch('[a-zA-Z0-9!@#%_+.-]{8,24}', password):
            raise ValueError('Password: 8–24 ASCII letters, digits or !@#%_+.-')
        import hashlib
        n, p, digest = quote(name), quote(password), quote(hashlib.md5(password.encode()).hexdigest())
        if sql('FFAccount', f'SELECT count(*) FROM accounts WHERE username={n};') != '0' or sql('FFMember', f'SELECT count(*) FROM tb_user WHERE mid={n};') != '0':
            raise ValueError('Username already exists')
        with edit(['FFAccount', 'FFMember']) as location:
            uid = int(sql('FFMember', f'INSERT INTO tb_user(mid,password,pwd,pvalues) VALUES({n},{p},{digest},0) RETURNING idnum;'))
            try:
                sql('FFAccount', f'INSERT INTO accounts(id,username,password) VALUES({uid},{n},{p});')
            except Exception:
                sql('FFMember', f'DELETE FROM tb_user WHERE idnum={uid} AND mid={n};')
                raise
        return {'backup': location, 'message': f'Created ordinary game account {name}'}
    if action == 'mall_edit':
        where = key_where(req.get('key', {}))
        values = req.get('values', {})
        limits = {'point': (1, 100000000), 'special_price': (0, 99999999),
                  'item_num': (1, 999), 'sell': (0, 1)}
        if not values or set(values) - limits.keys():
            raise ValueError('Unsupported mall field')
        old = rows('FFAccount', f'SELECT * FROM itemmall WHERE {where}')
        if len(old) != 1:
            raise ValueError('Mall row not found')
        updated = dict(old[0], **values)
        for k, v in values.items():
            integer(v, *limits[k])
        if updated['special_price'] and updated['special_price'] >= updated['point']:
            raise ValueError('Sale price must be zero (none), or less than regular price')
        setters = ','.join(f'{k}={v}' for k,v in values.items())
        with edit(['FFAccount']) as location:
            sql('FFAccount', f'BEGIN; UPDATE itemmall SET {setters} WHERE {where}; COMMIT;')
        return {'backup': location, 'message': 'Mall row saved and cache restart requested'}
    if action == 'mall_add':
        item = integer(req.get('item_id'), 1, 65535)
        category = integer(req.get('category'), 1, 44)
        price = integer(req.get('point'), 1, 100000000)
        quantity = integer(req.get('item_num'), 1, 999)
        text = Path('/root/hxsy/Data/db/S_Item.ini').read_bytes().decode('cp950')
        if not re.search(r'(?m)^' + str(item) + r'\|', text):
            raise ValueError('Item template does not exist in this server build')
        if sql('FFAccount',f'SELECT count(*) FROM itemmall WHERE item_group=6 AND money_unit=1 AND detail_type={category} AND item_id={item};') != '0':
            raise ValueError('This item is already listed in the chosen category')
        with edit(['FFAccount']) as location:
            index = int(sql('FFAccount',f'SELECT coalesce(max(item_index),0)+1 FROM itemmall WHERE item_group=6 AND money_unit=1 AND detail_type={category};'))
            integer(index,1,32767)
            sql('FFAccount',f'''BEGIN; INSERT INTO itemmall(item_id,item_group,detail_type,item_index,item_num,
                money_unit,point,special_price,num_limit,flags,level_limit,gender,sell,not_sell_date,sell_date,message,beginner_only_time,note)
                VALUES({item},6,{category},{index},{quantity},1,{price},0,0,0,0,-1,1,0,0,'',0,'dashboard:custom-listing'); COMMIT;''')
        return {'backup': location, 'message': 'Item listed in the existing client category; game cache restart requested'}
    if action == 'sale_begin':
        category = integer(req.get('category'), 1, 44)
        discount = integer(req.get('discount'), 1, 99)
        existing = rows('FFAccount', f'''SELECT item_group,detail_type,item_index,money_unit,point,special_price
            FROM itemmall WHERE item_group=6 AND money_unit=1 AND detail_type={category} AND point>1''')
        if not existing:
            raise ValueError('No discountable items here. Items priced at 1 AP cannot be discounted further.')
        with edit(['FFAccount']) as location:
            sql('FFAccount', f'''BEGIN; UPDATE itemmall SET special_price=greatest(1,floor(point::numeric*(100-{discount})/100)::int)
                WHERE item_group=6 AND money_unit=1 AND detail_type={category} AND point>1; COMMIT;''')
        return {'backup': location, 'restore': existing, 'message': f'Sale activated on {len(existing)} items'}
    if action == 'sale_prepare':
        category = integer(req.get('category'), 1, 44)
        return rows('FFAccount', f'''SELECT item_group,detail_type,item_index,money_unit,point,special_price
            FROM itemmall WHERE item_group=6 AND money_unit=1 AND detail_type={category} AND point>1''')
    if action == 'sale_end':
        original = req.get('restore', [])
        if not isinstance(original, list) or not 1 <= len(original) <= 20000:
            raise ValueError('Missing sale restoration snapshot')
        statements = []
        for row in original:
            where = key_where(row)
            price = integer(row['special_price'], 0, 99999999)
            statements.append(f'UPDATE itemmall SET special_price={price} WHERE {where};')
        with edit(['FFAccount']) as location:
            sql('FFAccount', 'BEGIN;' + ''.join(statements) + 'COMMIT;')
        return {'backup': location, 'message': 'Original sale prices restored'}
    raise ValueError('Unknown dashboard operation')


if __name__ == '__main__':
    import fcntl
    os.umask(0o077)
    try:
        request = json.load(sys.stdin)
        with open('/run/lock/ak-dashboard.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = run(request)
        print(json.dumps({'ok': True, 'result': result}))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
