"""VM-side deployment runner executed on the game VM.

Requires:
  /root/mall-f2p-catalog.json   built by ops/build-full-mall.py
  /root/mall-f2p-billing.sql    built by ops/install-full-mall.py

Order mirrors install-gear-catalog.py: offline check, backups, stop service,
apply billing rewrite (FFMember), wipe + repopulate itemmall (FFAccount),
verify, restart service.
"""
from pathlib import Path
import datetime, json, os, subprocess

os.umask(0o077)
config = json.loads(Path('/root/mall-f2p-catalog.json').read_text())
billing = Path('/root/mall-f2p-billing.sql').read_text()
MARKER = config['marker']
assert MARKER == 'codex:mall-f2p:v1' and config['item_group'] == 6
ITEMS = config['items']
assert ITEMS and len(ITEMS) < 32000
assert all(isinstance(i[k], int) for i in ITEMS for k in ('id', 'detail_type', 'index', 'money_unit', 'price'))
assert all(i['money_unit'] in (1, 2) and i['price'] >= 1 and i['id'] <= 65535 for i in ITEMS)


def sql(db, text):
    result = subprocess.run(
        ['runuser', '-u', 'postgres', '--', 'psql', '-X', '-q', '-tA',
         '-v', 'ON_ERROR_STOP=1', '-d', db],
        input=text, text=True, capture_output=True, cwd='/tmp')
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


if sql('FFDB1', 'SELECT count(*) FROM player_characters WHERE quit=0;') != '0':
    raise RuntimeError('Players must be offline for this deployment')
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = Path('/var/backups/aurakingdom') / ('pre-full-mall-' + stamp)
backup.mkdir(mode=0o700)
snapshot = sql('FFAccount',
               "SELECT coalesce(json_agg(row_to_json(t) ORDER BY row_to_json(t)::text)::text,'[]')"
               " FROM itemmall t;")
(backup / 'itemmall-full-snapshot.json').write_text(snapshot)
for database in ['FFAccount', 'FFDB1', 'FFMember']:
    with (backup / (database + '.dump')).open('wb') as out:
        subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', database],
                       stdout=out, check=True, cwd='/tmp')
subprocess.run(['systemctl', 'stop', 'aurakingdom'], check=True)
try:
    has_dblink = sql('FFMember',
                     "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace"
                     " WHERE n.nspname='public' AND p.proname='dblink_connect';")
    if has_dblink == '0':
        sql('FFMember', 'CREATE EXTENSION dblink;')
    sql('FFMember', billing)
    # wipe the entire item mall and insert the rebuilt F2P catalog
    statement = ("BEGIN; DELETE FROM itemmall; ")
    for start in range(0, len(ITEMS), 5000):
        chunk = ITEMS[start:start + 5000]
        rows = ["({id},6,{dt},{idx},1,{u},{p},0,0,0,0,-1,1,0,0,'',0,'{m}')".format(
                    id=i['id'], dt=i['detail_type'], idx=i['index'],
                    u=i['money_unit'], p=i['price'], m=MARKER)
                for i in chunk]
        statement += ("INSERT INTO itemmall(item_id,item_group,detail_type,item_index,"
                      "item_num,money_unit,point,special_price,num_limit,flags,level_limit,"
                      "gender,sell,not_sell_date,sell_date,message,beginner_only_time,note)"
                      " VALUES " + ','.join(rows) + ';')
    statement += ' COMMIT;'
    sql('FFAccount', statement)

    total = sql('FFAccount', 'SELECT count(*) FROM itemmall;')
    if total != str(len(ITEMS)):
        raise RuntimeError('Item mall row count mismatch after insert: %s != %d' % (total, len(ITEMS)))
    mutation = sql('FFAccount',
                   "SELECT count(*) FROM itemmall WHERE note <> '" + MARKER + "';")
    if mutation != '0':
        raise RuntimeError('Foreign itemmall rows survived the wipe: %s' % mutation)
    wallet_split = sql('FFAccount',
                       'SELECT money_unit || chr(32) || count(*) || chr(32) || min(point)'
                       ' || chr(32) || max(point) FROM itemmall GROUP BY money_unit ORDER BY money_unit;')
    functions = sql('FFMember',
                    "SELECT p.oid::regprocedure FROM pg_proc p JOIN pg_namespace n"
                    " ON n.oid=p.pronamespace WHERE n.nspname='public'"
                    " AND p.proname IN ('get_point_info','req_buy_item') ORDER BY 1;")
    report = {
        'marker': MARKER,
        'items': len(ITEMS),
        'code_total_before': 'snapshot file + pg_hack',
        'wallet_split': wallet_split.splitlines(),
        'functions': functions.splitlines(),
        'backup': str(backup),
        'validation': 'Database installed and rewired to character gold/bind_gold;'
                      ' in-game display and purchase NOT yet gameplay-tested',
    }
    Path('/root/full-mall-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
finally:
    subprocess.run(['systemctl', 'start', 'aurakingdom'], check=True)
