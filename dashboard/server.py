"""Loopback-only Aura Kingdom administration web app. Python standard library + existing SSH runtime."""
import concurrent.futures
import contextlib
import datetime as dt
import hashlib
import hmac
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'ops/runtime'))
import paramiko

DATA = ROOT / 'private/dashboard'
PORT = 8765
ORIGIN = f'http://127.0.0.1:{PORT}'
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)
MUTATION_LOCK = threading.Lock()
SESSIONS = {}
SESSION_LOCK = threading.Lock()
LOGIN_ATTEMPTS = []
JOBS = {}
JOB_LOCK = threading.Lock()


@contextlib.contextmanager
def connect_db():
    con = sqlite3.connect(DATA / 'dashboard.sqlite', timeout=30)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def setup():
    DATA.mkdir(parents=True, exist_ok=True)
    credential = DATA / 'admin.json'
    if not credential.exists():
        password, salt = secrets.token_urlsafe(18), secrets.token_hex(16)
        encoded = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 300000).hex()
        credential.write_text(json.dumps({'username': 'admin', 'salt': salt, 'hash': encoded}), encoding='utf-8')
        (DATA / 'LOGIN.txt').write_text(f'URL: {ORIGIN}\nUsername: admin\nPassword: {password}\n\nLocal dashboard credentials, separate from game accounts.\n', encoding='utf-8')
    with connect_db() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, time TEXT, action TEXT, status TEXT, details TEXT);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,name TEXT,kind TEXT,start TEXT,end TEXT,category INTEGER,
        discount INTEGER,status TEXT,error TEXT DEFAULT '',snapshot TEXT DEFAULT '[]');''')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def audit(action, status, detail):
    with connect_db() as db:
        db.execute('INSERT INTO audit(time,action,status,details) VALUES(?,?,?,?)', (now(), action, status, str(detail)[:3000]))


def remote(request):
    client = paramiko.SSHClient()
    client.load_host_keys(str(ROOT / 'private/known_hosts'))
    key = paramiko.Ed25519Key.from_private_key_file(str(ROOT / 'private/vm_ed25519'), password='""')
    try:
        client.connect('127.0.0.1', port=22222, username='root', pkey=key,
                       look_for_keys=False, allow_agent=False, timeout=10)
        source = (HERE / 'agent.py').read_text(encoding='utf-8')
        stdin, stdout, stderr = client.exec_command('python3 -c ' + shlex.quote(source), timeout=600)
        stdin.write(json.dumps(request))
        stdin.flush()
        stdin.channel.shutdown_write()
        payload = stdout.read().decode()
        exit_code = stdout.channel.recv_exit_status()
        if exit_code:
            raise RuntimeError('Guest administration command failed: ' + stderr.read().decode()[-500:])
        response = json.loads(payload)
        if not response['ok']:
            raise ValueError(response['error'])
        return response['result']
    finally:
        client.close()


def metadata():
    sections = json.loads((ROOT / 'docs/gear-catalog-split.json').read_text(encoding='utf-8'))['sections']
    names = {}
    # Translation table has multiline descriptions; split on record starts, not every newline.
    import re
    # Resolve actual client path/casing without exposing general filesystem access to HTTP.
    candidates = list((ROOT / 'client').glob('*/data/db/T_Item.ini')) + list((ROOT / 'client').glob('*/Data/db/T_Item.ini'))
    if candidates:
        text = candidates[0].read_bytes().decode('cp950', errors='replace')
        for record in re.split(r'(?m)(?=^\d+\|)', text)[1:]:
            fields = record.split('|')
            if len(fields)>1:
                names[fields[0]] = fields[1]
    return {'sections': sections, 'items': names}


META = None


def events():
    with connect_db() as db:
        return [dict(r) for r in db.execute('SELECT id,name,kind,start,end,category,discount,status,error FROM events ORDER BY start DESC')]


def save_event(data):
    name = str(data.get('name', '')).strip()
    if not 1 <= len(name) <= 100:
        raise ValueError('Enter an event name (up to 100 characters)')
    if data.get('kind') not in ['maintenance', 'sale']:
        raise ValueError('Choose a supported event type')
    start, end = [dt.datetime.fromisoformat(data[k].replace('Z', '+00:00')) for k in ['start', 'end']]
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError('Event times must include a timezone')
    if start <= dt.datetime.now(dt.timezone.utc) or end <= start:
        raise ValueError('Choose a future start and an end after the start')
    category, discount = data.get('category', 1), data.get('discount', 10)
    if type(category) is not int or not 1 <= category <= 44 or type(discount) is not int or not 1 <= discount <= 99:
        raise ValueError('Invalid sale category or percentage')
    with connect_db() as db:
        if data['kind'] == 'sale' and db.execute("SELECT 1 FROM events WHERE kind='sale' AND category=? AND status NOT IN ('completed','cancelled') AND start<? AND end>?", (category,end.astimezone(dt.timezone.utc).isoformat(),start.astimezone(dt.timezone.utc).isoformat())).fetchone():
            raise ValueError('Another sale overlaps this category')
        ident = secrets.token_hex(8)
        db.execute('INSERT INTO events(id,name,kind,start,end,category,discount,status) VALUES(?,?,?,?,?,?,?,?)',
                   (ident,name,data['kind'],start.astimezone(dt.timezone.utc).isoformat(),end.astimezone(dt.timezone.utc).isoformat(),category,discount,'scheduled'))
    return {'message': 'Event scheduled. Dashboard must stay running for sale automation.', 'id': ident}


def execute(action, data):
    with MUTATION_LOCK:
        if action == 'event_create':
            result = save_event(data)
        elif action == 'event_cancel':
            with connect_db() as db:
                row = db.execute('SELECT * FROM events WHERE id=?', (data.get('id'),)).fetchone()
                if not row:
                    raise ValueError('Event not found')
                if row['kind'] == 'sale' and row['status'] in ['active', 'ending']:
                    remote({'action': 'sale_end', 'restore': json.loads(row['snapshot'])})
                db.execute("UPDATE events SET status='cancelled',error='' WHERE id=?", (row['id'],))
            result = {'message': 'Event cancelled; active sale restored if needed'}
        elif action == 'service' and data.get('operation') == 'start':
            # Existing VM launcher also handles a powered-off VM.
            p = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File', str(ROOT/'ops/Start-Server.ps1')], cwd=ROOT, capture_output=True, text=True, timeout=240)
            if p.returncode:
                raise ValueError('Server startup failed. Check VirtualBox and the Operations logs.')
            result = {'message': 'VM and game service started. Allow a minute for the channel.'}
        else:
            if action in ['mall_edit','mall_add']:
                key = data.get('key', {}) if action=='mall_edit' else dict(item_group=6,money_unit=1,detail_type=data.get('category'))
                with connect_db() as db:
                    if db.execute("SELECT 1 FROM events WHERE kind='sale' AND category=? AND status IN ('active','ending')", (key.get('detail_type'),)).fetchone() and key.get('item_group') == 6 and key.get('money_unit') == 1:
                        raise ValueError('End the active category sale before editing its stock')
                if action == 'mall_add' and str(data.get('item_id')) not in META['items']:
                    raise ValueError('Item ID is missing from the installed client translation table')
            result = remote(dict(data, action=action))
        audit(action, 'success', json.dumps(result, ensure_ascii=False))
        return result


def submit(action, data):
    ident = secrets.token_hex(12)
    with JOB_LOCK:
        # Bound in-memory retention; jobs are also recorded durably in audit.
        if len(JOBS)>500:
            for key in list(JOBS)[:100]:
                if JOBS[key]['status'] != 'running':
                    del JOBS[key]
        JOBS[ident] = {'status': 'running', 'action': action}
    def work():
        try:
            result = execute(action, data)
            job = {'status': 'done', 'result': result}
        except Exception as exc:
            audit(action, 'error', str(exc))
            job = {'status': 'error', 'error': str(exc)}
        with JOB_LOCK:
            JOBS[ident] = job
    POOL.submit(work)
    return {'job': ident}


def tick():
    with MUTATION_LOCK:
        with connect_db() as db:
            pending = [dict(r) for r in db.execute("SELECT * FROM events WHERE status IN ('scheduled','waiting','active','ending')")]
        for event in pending:
            timestamp = now()
            if timestamp < event['start']:
                continue
            status, error, snapshot = event['status'], '', event['snapshot']
            try:
                if event['kind'] == 'maintenance':
                    # Calendar only: never silently stop a running game.
                    status = 'completed' if timestamp >= event['end'] else 'active'
                elif status in ['scheduled', 'waiting']:
                    if timestamp >= event['end']:
                        status, error = 'cancelled', 'Window elapsed before sale could start'
                    else:
                        # Persist a recovery snapshot BEFORE making any game change.
                        original = remote({'action': 'sale_prepare', 'category': event['category']})
                        if not original:
                            raise ValueError('Category has no items above 1 AP; no sale can be applied')
                        snapshot = json.dumps(original)
                        with connect_db() as db:
                            db.execute("UPDATE events SET snapshot=?,status='ending',error='Activation interrupted; restoration required' WHERE id=?", (snapshot,event['id']))
                        result = remote({'action':'sale_begin','category':event['category'],'discount':event['discount']})
                        status = 'active'
                        audit('event_started', 'success', event['name'] + ': ' + result['message'])
                elif timestamp >= event['end'] or status == 'ending':
                    remote({'action': 'sale_end', 'restore': json.loads(snapshot)})
                    status = 'completed'
                    audit('event_ended','success',event['name'])
            except Exception as exc:
                error = str(exc)
                # Once a restoration snapshot is written, always prefer restoring it.
                with connect_db() as db:
                    saved = db.execute('SELECT status,snapshot FROM events WHERE id=?', (event['id'],)).fetchone()
                if saved['status'] == 'ending' or status in ['active','ending']:
                    status = 'ending'
                    snapshot = saved['snapshot']
                else:
                    status = 'waiting'
            with connect_db() as db:
                db.execute('UPDATE events SET status=?,error=?,snapshot=? WHERE id=?', (status,error,snapshot,event['id']))


def scheduler():
    while True:
        try:
            tick()
        except Exception as exc:
            audit('scheduler', 'error', str(exc))
        time.sleep(30)


class Handler(BaseHTTPRequestHandler):
    server_version = 'AKAdmin'

    def log_message(self, fmt, *args):
        # Do not log requests, login bodies, cookies or game passwords.
        pass

    def send(self, code, data, content_type='application/json; charset=utf-8', extra=None):
        body = json.dumps(data,ensure_ascii=False).encode() if content_type.startswith('application/json') else data
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key,value in (extra or {}).items():
            self.send_header(key,value)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie',''))
            token = jar['ak_admin'].value if 'ak_admin' in jar else ''
        except cookies.CookieError:
            return None
        with SESSION_LOCK:
            session = SESSIONS.get(token)
            if session and session['expires'] > time.time():
                return dict(session,token=token)
        return None

    def valid_host(self):
        return self.headers.get('Host') in [f'127.0.0.1:{PORT}', f'localhost:{PORT}']

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {'error': 'Invalid host'})
        target = urlparse(self.path)
        if target.path in ['/', '/app.js', '/style.css']:
            filename, mime = {'/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','application/javascript'), '/style.css':('style.css','text/css')}[target.path]
            return self.send(200, (HERE/'static'/filename).read_bytes(), mime)
        session = self.session()
        if not session:
            return self.send(401, {'error': 'Sign in to continue'})
        try:
            route = target.path.removeprefix('/api/')
            if route == 'session':
                result = {'username':'admin','csrf':session['csrf']}
            elif route == 'meta':
                result = META
            elif route == 'events':
                result = events()
            elif route == 'audit':
                with connect_db() as db:
                    result = [dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]
            elif route.startswith('jobs/'):
                with JOB_LOCK:
                    result = JOBS.get(route.split('/')[-1])
                if result is None:
                    return self.send(404, {'error': 'Unknown job'})
            elif route in ['status','players','accounts','mall','logs','backups','bots']:
                params = {k:v[0] for k,v in parse_qs(target.query).items()}
                for key in ['page','category','item_id','limit']:
                    if params.get(key):
                        params[key] = int(params[key])
                if route=='mall' and params.get('search'):
                    term = params.pop('search').strip().casefold()[:100]
                    if term.isdigit():
                        params['item_id'] = int(term)
                    else:
                        params['item_ids'] = [int(i) for i,name in META['items'].items() if term in name.casefold() and 1<=int(i)<=65535]
                result = remote(dict(params, action=route))
            else:
                return self.send(404, {'error':'Not found'})
            self.send(200,result)
        except Exception as exc:
            self.send(400,{'error':str(exc)})

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') != ORIGIN:
            return self.send(403, {'error':'Open the dashboard at ' + ORIGIN})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 32768 or self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                raise ValueError('Expected a JSON request smaller than 32 KB')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data,dict):
                raise ValueError('Expected a JSON object')
            route = urlparse(self.path).path.removeprefix('/api/')
            if route == 'login':
                current = time.time()
                LOGIN_ATTEMPTS[:] = [t for t in LOGIN_ATTEMPTS if t > current-300]
                if len(LOGIN_ATTEMPTS)>=10:
                    return self.send(429,{'error':'Too many attempts. Try again in five minutes.'})
                stored = json.loads((DATA/'admin.json').read_text())
                supplied = str(data.get('password',''))[:256]
                digest = hashlib.pbkdf2_hmac('sha256',supplied.encode(),bytes.fromhex(stored['salt']),300000).hex()
                if data.get('username') != stored['username'] or not hmac.compare_digest(digest,stored['hash']):
                    LOGIN_ATTEMPTS.append(current)
                    return self.send(401,{'error':'Incorrect username or password'})
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                with SESSION_LOCK:
                    for old in list(SESSIONS):
                        if SESSIONS[old]['expires'] < current:
                            del SESSIONS[old]
                    SESSIONS[token] = {'csrf':csrf,'expires':current+8*3600}
                return self.send(200,{'csrf':csrf},extra={'Set-Cookie':f'ak_admin={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
            session = self.session()
            if not session:
                return self.send(401,{'error':'Sign in to continue'})
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
                return self.send(403,{'error':'Refresh the dashboard and try again'})
            if route == 'logout':
                with SESSION_LOCK:
                    SESSIONS.pop(session['token'],None)
                return self.send(200,{'ok':True},extra={'Set-Cookie':'ak_admin=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            if route not in ['service','backup','player_edit','account_create','mall_edit','mall_add','event_create','event_cancel','bot_control']:
                return self.send(404,{'error':'Not found'})
            self.send(202,submit(route,data))
        except Exception as exc:
            self.send(400,{'error':str(exc)})


if __name__ == '__main__':
    setup()
    META = metadata()
    server = ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    threading.Thread(target=scheduler,daemon=True).start()
    print(f'Aura Kingdom dashboard: {ORIGIN}',flush=True)
    print(f'Login details: {DATA / "LOGIN.txt"}',flush=True)
    server.serve_forever()
