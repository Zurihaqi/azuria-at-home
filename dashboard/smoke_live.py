"""Local HTTP + real guest read/backup smoke test; never edits characters or mall stock."""
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.request
import urllib.error

BASE='http://127.0.0.1:8765'
root=Path(__file__).resolve().parent.parent
jar=http.cookiejar.CookieJar()
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf=''

def call(path,data=None):
    headers={}
    body=None
    if data is not None:
        headers={'Content-Type':'application/json','Origin':BASE,'X-CSRF-Token':csrf}
        body=json.dumps(data).encode()
    req=urllib.request.Request(BASE+'/api/'+path,body,headers)
    with client.open(req,timeout=180) as response:
        return json.load(response)

def job(action,data):
    ident=call(action,data)['job']
    for _ in range(180):
        result=call('jobs/'+ident)
        if result['status']=='done':
            return result['result']
        if result['status']=='error':
            raise RuntimeError(result['error'])
        time.sleep(1)
    raise TimeoutError('Job did not finish')

password=(root/'private/dashboard/LOGIN.txt').read_text().split('Password: ')[1].splitlines()[0]
csrf=call('login',dict(username='admin',password=password))['csrf']
report={}
for action in ['status','players','accounts','mall?category=44','mall?search=Astral%20Sovereign','events','logs','backups','audit']:
    result=call(action)
    report[action]=len(result) if isinstance(result,list) else 'ok'
assert call('status')['active']
assert len(call('mall?search=Astral%20Sovereign')['items'])>=11
report['backup']=job('backup',{})
call('logout',{})
try:
    call('status')
    raise AssertionError('Logout did not invalidate session')
except urllib.error.HTTPError as error:
    assert error.code==401
report['logout']='session invalidated'
(root/'docs/dashboard-live-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
