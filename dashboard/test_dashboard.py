"""Regression checks for auth, bounded SQL edits and crash-safe sale restoration."""
import datetime as dt
import http.client
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import server
import agent
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bots'))
from reporting import Reporter


class BotMonitoring(unittest.TestCase):
    def test_reported_position_is_numeric_and_uses_its_own_timestamp(self):
        now = time.time()
        data = dict(map=2, position=dict(x=288.25, y=297.3, map=2, observed_at=now))
        position = agent.bot_position(data, False, 'arden', True)
        self.assertEqual((position['x'], position['y'], position['source'], position['stale']),
                         (288.2, 297.3, 'native', False))
        data['position']['observed_at'] = now - 60
        self.assertTrue(agent.bot_position(data, False, 'arden', True)['stale'])
        data['position']['x'] = float('nan')
        self.assertIsNone(agent.bot_position(data, False, 'arden', True))

    def test_saved_position_is_labeled_and_uses_only_fixed_bot_id(self):
        with patch.object(agent, 'rows', return_value=[dict(node_id=2,x=288.3,y=297.3)]) as query:
            position = agent.bot_position(dict(map=2, character_id='malformed'), True, 'arden', True)
            self.assertEqual(position['source'], 'saved')
            self.assertTrue(position['stale'])
            self.assertIn('id=50000003', query.call_args.args[1])
            self.assertIsNone(agent.bot_position(dict(map=3), True, 'arden', True))

    def test_log_position_cannot_cross_a_respawn_or_map_change(self):
        position = dict(time=time.time(), message='Native movement endpoint confirmed at (260.25, 473.75)')
        result = agent.bot_position(dict(map=2), False, 'arden', True, [position])
        self.assertEqual((result['x'], result['y']), (260.2, 473.8))
        for barrier in ('Native respawn confirmed; character remains connected.', 'Native map entry: node=3'):
            self.assertIsNone(agent.bot_position(dict(map=2), False, 'arden', True,
                                                [dict(message=barrier), position]))

    def test_unbuffered_python_bots_are_detected_without_matching_inline_code(self):
        class Process:
            def __init__(self, args):
                self.args = b'\0'.join(args)
            def read_bytes(self):
                return self.args
        script = b'/opt/ak-bot-prototype/probe_login.py'
        for args, profile, expected in (
            ([b'/usr/bin/python3',b'-u',script,b'--normal-world'], 'awan', True),
            ([b'/usr/bin/python3',b'-u',script,b'--profile',b'arden'], 'arden', True),
            ([b'/usr/bin/python3',b'-u',script,b'--profile',b'arden'], 'awan', False),
            ([b'/usr/bin/python3',b'-c',script], 'awan', False)):
            with patch.object(agent.Path,'glob',return_value=[Process(args)]):
                self.assertEqual(agent.bot_process_running(profile),expected)

    def setUp(self):
        root=server.ROOT/'private/dashboard-tests'
        root.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=root)
        self.base=Path(self.tmp.name)
        (self.base/'run/pilot').mkdir(parents=True)
        (self.base/'logs').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_bot_logs_are_newest_first_and_keep_the_newest_limit(self):
        events=[dict(time=n,level='info',message=f'Entry {n}',bot='Pilot') for n in range(30)]
        (self.base/'run/pilot/events-public.jsonl').write_text(
            '\n'.join(json.dumps(row) for row in events)+'\n')
        result=self.status()
        self.assertEqual([r['time'] for r in result['logs']],list(range(29,9,-1)))

    def test_server_journal_requests_newest_first(self):
        with patch.object(agent,'command',return_value='latest\nearlier') as command:
            self.assertEqual(agent.run({'action':'logs'})['text'],'latest\nearlier')
        self.assertIn('--reverse',command.call_args.args[0])

    def status(self, lab=False, running=False):
        with patch.object(agent,'BOT_BASE',self.base), patch.object(agent.subprocess,'run') as run, patch.object(agent,'bot_process_running',return_value=running):
            run.return_value.returncode=0 if lab else 3
            return agent.run({'action':'bots','limit':20})

    def test_stopped_process_never_looks_online_and_credentials_are_excluded(self):
        pilot=self.base/'run/pilot'
        (pilot/'status-public.json').write_text(json.dumps(dict(phase='online',name='AwanBotLab',updated_at=time.time(),password='private-canary',task='password=private-canary')))
        (pilot/'events-public.jsonl').write_text(json.dumps(dict(time=time.time(),message='password=private-canary',level='error',password='private-canary'))+'\n')
        result=self.status()
        self.assertEqual(result['runtime'],'stopped')
        self.assertEqual(result['online'],0)
        self.assertNotIn('private-canary',json.dumps(result))

    def test_stale_heartbeat_and_recorded_requests_are_not_successes(self):
        (self.base/'run/pilot/status-public.json').write_text(json.dumps(dict(phase='online',updated_at=time.time()-60)))
        (self.base/'logs/client-gameplay.jsonl').write_text('malformed\n'+json.dumps(dict(time=time.time(),opcode=2,fields=[2,2001,65535],payload='private-canary'))+'\n')
        result=self.status(lab=True,running=True)
        self.assertEqual(result['runtime'],'stale')
        self.assertEqual(result['online'],0)
        self.assertIn('result not implied',result['logs'][0]['message'])
        self.assertNotIn('private-canary',json.dumps(result))

    def test_reporter_logs_progress_failure_and_excludes_session_material(self):
        reporter=Reporter(self.base/'run/pilot')
        reporter.update(name='AwanBotLab',map=610,level=1,phase='online')
        reporter.message('Native quest update: (0, 2001, 1)')
        reporter.message('Native quest update: password=private-canary')
        reporter.message('World ticket received: private-canary')
        reporter.message('Protocol probe stopped: Repeated native movement corrections; route paused')
        result=self.status(lab=True,running=True)
        self.assertEqual(result['runtime'],'failed')
        self.assertEqual(result['bots'][0]['map'],610)
        self.assertIn('movement corrections',result['bots'][0]['last_failure'])
        self.assertNotIn('private-canary',json.dumps(result))

    def test_log_reads_are_bounded_and_limit_is_validated(self):
        path=self.base/'logs/client-gameplay.jsonl'
        path.write_text(('x'*400000)+'\n'+json.dumps(dict(opcode=2,fields=[1,1001,65535]))+'\n')
        self.assertEqual(len(agent.bot_tail(path)),1)
        for value in (True,0,501,'20;ls'):
            with self.assertRaises(ValueError):
                agent.bots_status(value)


class GuestValidation(unittest.TestCase):
    def test_numbers_reject_booleans_and_injection(self):
        for value in [True, '1; DROP TABLE itemmall', 0, 100]:
            with self.assertRaises(ValueError):
                agent.integer(value,1,99)

    def test_quote_escapes_sql(self):
        self.assertEqual(agent.quote("O'Brien"), "'O''Brien'")
        with self.assertRaises(ValueError):
            agent.quote('x\x00y')

    def test_online_guard_never_stops_server(self):
        with patch.object(agent,'online',return_value=[{'given_name':'Zrymund'}]), patch.object(agent,'command') as command:
            with self.assertRaisesRegex(ValueError,'Log everyone out'):
                with agent.edit(['FFDB1']):
                    self.fail('Edit entered while online')
            command.assert_not_called()

    def test_edit_backs_up_before_write_and_restarts_after_failure(self):
        steps=[]
        with patch.object(agent,'online',return_value=[]), patch.object(agent,'active',return_value=True), patch.object(agent,'command',side_effect=lambda args:steps.append(args[1])), patch.object(agent,'backup',side_effect=lambda db:steps.append('backup') or '/backup'):
            with self.assertRaises(RuntimeError):
                with agent.edit(['FFDB1']):
                    steps.append('write')
                    raise RuntimeError('write failed')
        self.assertEqual(steps,['stop','backup','write','start'])

    def test_mall_rejects_price_equal_to_regular(self):
        row={'point':1,'special_price':0}
        key=dict(item_group=6,detail_type=1,item_index=1001,money_unit=1)
        with patch.object(agent,'rows',return_value=[row]), patch.object(agent,'edit') as edit:
            with self.assertRaisesRegex(ValueError,'less than regular'):
                agent.run({'action':'mall_edit','key':key,'values':{'special_price':1}})
            edit.assert_not_called()

    def test_player_rejects_unsupported_fields_and_level(self):
        for values in [{'exp':999999},{'level':150},{'gold':2147483647}]:
            with self.assertRaises(ValueError):
                agent.run({'action':'player_edit','id':50000001,'values':values})


class BotControlAction(unittest.TestCase):
    def control(self, **req):
        return agent.run(dict(action='bot_control', **req))

    def test_unknown_operation_or_profile_never_runs_a_command(self):
        with patch.object(agent,'command') as command:
            for data in [{'operation':'restart','profile':'awan'},{'operation':'start','profile':'lab'},
                         {'operation':'start','profile':'awan; rm -rf'},
                         {},{'profile':'arden'},{'operation':'START','profile':'arden'}]:
                payload = dict(data)
                payload.setdefault('profile','awan')
                with self.assertRaises(ValueError):
                    self.control(**payload)
            command.assert_not_called()

    def test_start_requires_the_game_service_first(self):
        with patch.object(agent,'active',return_value=False), patch.object(agent,'command') as command, \
             patch.object(agent,'bot_json',return_value={'enabled':True}):
            with self.assertRaisesRegex(ValueError,'game service'):
                self.control(operation='start',profile='awan')
            command.assert_not_called()

    def test_start_requires_enabled_normal_world_access(self):
        with patch.object(agent,'active',return_value=True), patch.object(agent,'command') as command, \
             patch.object(agent,'bot_json',return_value={'enabled':False}):
            with self.assertRaisesRegex(ValueError,'not enabled'):
                self.control(operation='start',profile='arden')
            command.assert_not_called()

    def test_start_runs_the_fixed_control_script_with_the_profile(self):
        with patch.object(agent,'active',return_value=True), \
             patch.object(agent,'bot_json',return_value={'enabled':True}) as world, \
             patch.object(agent,'command',return_value=json.dumps({'message':'started'})) as command:
            result = self.control(operation='start',profile='arden')
        self.assertEqual(result,{'message':'started'})
        self.assertEqual(command.call_args.args[0],
                         ['python3','/opt/ak-bot-prototype/bot_control.py','start','arden'])
        self.assertEqual(world.call_args.args[0],Path('/etc/ak-bots/arden-world.json'))

    def test_stop_is_allowed_without_an_active_game_and_reports_refusals(self):
        for payload in ({'message':'not running'}, {'error':'No recorded bot deployment'}):
            with patch.object(agent,'command',return_value=json.dumps(payload)):
                if payload.get('error'):
                    with self.assertRaisesRegex(ValueError,'No recorded bot deployment'):
                        self.control(operation='stop',profile='awan')
                else:
                    self.assertEqual(self.control(operation='stop',profile='awan'),{'message':'not running'})


class LocalState(unittest.TestCase):
    def setUp(self):
        test_root=server.ROOT/'private/dashboard-tests'
        test_root.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=test_root)
        self.old=server.DATA
        server.DATA=Path(self.tmp.name)
        server.setup()
        server.SESSIONS.clear()
        server.LOGIN_ATTEMPTS.clear()

    def tearDown(self):
        server.DATA=self.old
        self.tmp.cleanup()

    def event(self,kind='sale'):
        start=dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5)
        return dict(name='Test event',kind=kind,start=start.isoformat(),end=(start+dt.timedelta(hours=1)).isoformat(),category=1,discount=20)

    def make_due(self,ident):
        with server.connect_db() as db:
            db.execute('UPDATE events SET start=? WHERE id=?',((dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=5)).isoformat(),ident))

    def test_overlapping_sales_blocked(self):
        server.save_event(self.event())
        with self.assertRaisesRegex(ValueError,'overlaps'):
            server.save_event(self.event())

    def test_sale_snapshot_is_durable_before_game_mutation(self):
        ident=server.save_event(self.event())['id'];self.make_due(ident)
        snapshot=[dict(item_group=6,detail_type=1,item_index=1,money_unit=1,point=100,special_price=0)]
        calls=[]
        def remote(req):
            calls.append(req['action'])
            if req['action']=='sale_prepare':
                return snapshot
            if req['action']=='sale_begin':
                with server.connect_db() as db:
                    row=db.execute('SELECT * FROM events WHERE id=?',(ident,)).fetchone()
                self.assertEqual(json.loads(row['snapshot']),snapshot)
                self.assertEqual(row['status'],'ending')
                raise ConnectionError('Connection interrupted')
            if req['action']=='sale_end':
                self.assertEqual(req['restore'],snapshot)
                return {'message':'Restored'}
            self.fail('Unexpected remote call')
        with patch.object(server,'remote',side_effect=remote):
            server.tick()
            self.assertEqual(server.events()[0]['status'],'ending')
            server.tick()
        self.assertEqual(server.events()[0]['status'],'completed')
        self.assertEqual(calls,['sale_prepare','sale_begin','sale_end'])

    def test_maintenance_calendar_does_not_stop_server(self):
        ident=server.save_event(self.event('maintenance'))['id'];self.make_due(ident)
        with patch.object(server,'remote') as remote:
            server.tick()
            remote.assert_not_called()
        self.assertEqual(server.events()[0]['status'],'active')

    def test_http_auth_origin_csrf_and_private_paths(self):
        httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        def request(method,path,data=None,headers=None):
            c=http.client.HTTPConnection('127.0.0.1',httpd.server_port)
            h={'Host':'127.0.0.1:8765'}
            h.update(headers or {})
            body=None
            if data is not None:
                body=json.dumps(data);h['Content-Type']='application/json'
            c.request(method,path,body=body,headers=h)
            r=c.getresponse();payload=r.read();status=r.status;head=dict(r.getheaders());c.close()
            return status,payload,head
        try:
            self.assertEqual(request('GET','/api/status')[0],401)
            self.assertEqual(request('GET','/api/bots')[0],401)
            self.assertEqual(request('GET','/private/dashboard/LOGIN.txt')[0],401)
            self.assertEqual(request('GET','/',headers={'Host':'evil.example'})[0],403)
            credentials=(server.DATA/'LOGIN.txt').read_text()
            password=credentials.split('Password: ')[1].splitlines()[0]
            self.assertEqual(request('POST','/api/login',dict(username='admin',password=password),{'Origin':'https://evil.example'})[0],403)
            code,body,head=request('POST','/api/login',dict(username='admin',password=password),{'Origin':server.ORIGIN})
            self.assertEqual(code,200)
            cookie=head['Set-Cookie'].split(';')[0]
            self.assertIn('HttpOnly',head['Set-Cookie']);self.assertIn('SameSite=Strict',head['Set-Cookie'])
            self.assertEqual(request('POST','/api/backup',{}, {'Origin':server.ORIGIN,'Cookie':cookie})[0],403)
            self.assertEqual(request('GET','/private/dashboard/LOGIN.txt',headers={'Cookie':cookie})[0],404)
            csrf=json.loads(body)['csrf']
            with patch.object(server,'remote',return_value={'runtime':'stopped','logs':[]}) as remote:
                self.assertEqual(request('GET','/api/bots?limit=20',headers={'Cookie':cookie})[0],200)
                remote.assert_called_once_with({'action':'bots','limit':20})
            self.assertEqual(request('POST','/api/bots/action',{'operation':'start'}, {'Origin':server.ORIGIN,'Cookie':cookie,'X-CSRF-Token':csrf})[0],404)
            self.assertEqual(request('POST','/api/logout',{}, {'Origin':server.ORIGIN,'Cookie':cookie,'X-CSRF-Token':csrf})[0],200)
            self.assertEqual(request('GET','/api/status',headers={'Cookie':cookie})[0],401)
        finally:
            httpd.shutdown();httpd.server_close()


if __name__=='__main__':
    unittest.main(verbosity=2)
