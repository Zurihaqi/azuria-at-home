"""Read-only live bot-monitoring check; never starts bots or game maintenance."""
import http.cookiejar
import json
from pathlib import Path
import urllib.request
import urllib.error

root = Path(__file__).resolve().parent.parent
base = 'http://127.0.0.1:8765'
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
csrf = ''


def call(path, data=None):
    headers = {}
    body = None
    if data is not None:
        headers = {'Content-Type':'application/json', 'Origin':base, 'X-CSRF-Token':csrf}
        body = json.dumps(data).encode()
    with client.open(urllib.request.Request(base + '/api/' + path, body, headers), timeout=30) as response:
        return json.load(response)


try:
    call('bots')
    raise AssertionError('Bot feed must require sign-in')
except urllib.error.HTTPError as error:
    assert error.code == 401
password = (root/'private/dashboard/LOGIN.txt').read_text().split('Password: ')[1].splitlines()[0]
csrf = call('login', {'username':'admin', 'password':password})['csrf']
try:
    result = call('bots?limit=250')
    assert result['mode'] == 'prototype'
    if result['production_enabled']:
        assert result['world'] == 'normal'
        assert result['bots'][0]['name'] == 'Awan'
    else:
        assert result['runtime'] == 'stopped' and result['online'] == 0
    assert len(result['logs']) <= 250
    assert password not in json.dumps(result)
    assert call('status')['active']
    report = {'authenticated_feed':'passed', 'runtime':result['runtime'],
              'world':result.get('world','isolated'),
              'online':result['online'], 'history_entries':len(result['logs']),
              'game_server_active':True}
    report['positions'] = [dict(name=bot['name'], map=bot.get('map'), position=bot.get('position'))
                           for bot in result['bots']]
    for bot in result['bots']:
        point = bot.get('position')
        if point is not None:
            assert type(point['x']) in (int, float) and type(point['y']) in (int, float)
            assert point['source'] in ('native', 'saved')
            assert point['source'] != 'saved' or point['stale'] is True
    (root/'docs/bot-dashboard-live-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
finally:
    call('logout', {})
