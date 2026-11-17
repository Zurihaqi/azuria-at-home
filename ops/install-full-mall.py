"""Deploy the F2P item mall (marker codex:mall-f2p:v1).

Wipes FFAccount.itemmall, inserts the rebuilt catalog from
docs/mall-f2p-catalog.json, and rewrites the FFMember billing functions
(get_point_info / req_buy_item) to bill character gold and bind_gold.

Usage:  python ops/install-full-mall.py --yes
(--yes is required: this deletes every existing itemmall row after backing up.)

Steps:
  1. validate the built catalog
  2. push catalog + billing SQL + VM runner into /root on the VM
  3. run the VM-side installer (offline check, backups, stop service,
     apply SQL, verify, restart service)
  4. fetch the install report into docs/
  5. relabel T_TextIndex.ini slots (61025-61043) into the new category names
"""
from pathlib import Path
import datetime, json, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parent.parent
TEMP = Path(tempfile.gettempdir()) / 'azuria-mall'
MARKER = 'codex:mall-f2p:v1'
LABEL_BASE = 61000

BILLING_SQL = """BEGIN;

DROP FUNCTION IF EXISTS get_point_info(character varying);
DROP FUNCTION IF EXISTS req_buy_item(character varying, character varying, integer, character varying, integer, character varying, integer, integer);
DROP FUNCTION IF EXISTS req_buy_item(character varying, character varying, integer, character varying, integer, character varying, integer, integer, integer);

-- F2P wallet: the two mall balances are character gold and bind_gold.
-- 1 gold = 1000 base units (CItemFactory::NormalizeGoldString divides by 1000).
CREATE FUNCTION get_point_info(ppAccountID character varying) RETURNS record
    LANGUAGE plpgsql STABLE
    AS $gf$
DECLARE
  pAccountID varchar(20);
  rec record;
BEGIN
  pAccountID := lower(ppAccountID);
  BEGIN
    PERFORM dblink_connect_u('mwallet','dbname=FFDB1');
    SELECT INTO rec g, b FROM dblink('mwallet',
        'SELECT (gold/1000), (bind_gold/1000) FROM player_characters'
        ' WHERE lower(account_name) = ' || quote_literal(pAccountID) ||
        ' AND COALESCE(deleted_time,0) = 0'
        ' ORDER BY COALESCE(is_itemmall_character,0) DESC, last_saving_time DESC NULLS LAST LIMIT 1',
        false) AS w(g integer, b integer);
    PERFORM dblink_disconnect('mwallet');
    IF NOT FOUND THEN
      rec := (0, 0);
    END IF;
    RETURN rec;
  EXCEPTION WHEN OTHERS THEN
    BEGIN PERFORM dblink_disconnect('mwallet'); EXCEPTION WHEN OTHERS THEN NULL; END;
    RAISE;
  END;
END;
$gf$;

-- Buy request from the gateway.  The wallet is derived from the itemmall row
-- (money_unit 1 = gold, 2 = bind gold) and NOT from the client-supplied
-- buy_type, so the shopper cannot pay gear in silver or potions in gold.
-- The item must exist in the rebuilt catalog or the purchase is refused.
CREATE FUNCTION req_buy_item(ppAccountID character varying,
                             pServerIP character varying,
                             pItemID integer,
                             pCharName character varying,
                             pBuyPoint integer,
                             pClientIP character varying,
                             pBuyType integer,
                             pAmount integer) RETURNS record
    LANGUAGE plpgsql
    AS $rf$
DECLARE
  pAccountID varchar(20);
  pChar varchar(32);
  rid integer;
  rgold integer;
  rbind integer;
  unit smallint;
  spend integer;
  afterg integer;
  afterb integer;
BEGIN
  pAccountID := lower(ppAccountID);
  pChar := lower(pCharName);
  IF pBuyPoint IS NULL OR pBuyPoint <= 0 THEN
    RAISE EXCEPTION 'req_buy_item: refused non-positive spend %', pBuyPoint;
  END IF;
  BEGIN
    PERFORM dblink_connect_u('mchar','dbname=FFDB1');
    SELECT INTO rid, rgold, rbind FROM dblink('mchar',
        'SELECT id, gold, bind_gold FROM player_characters'
        ' WHERE lower(given_name) = ' || quote_literal(pChar) ||
        ' AND lower(account_name) = ' || quote_literal(pAccountID) ||
        ' AND COALESCE(deleted_time,0) = 0'
        ' ORDER BY last_saving_time DESC NULLS LAST LIMIT 1',
        false) AS ch(id integer, gold integer, bind_gold integer);
    IF rid IS NULL THEN
      RAISE EXCEPTION 'req_buy_item: character % not found for account %', pChar, pAccountID;
    END IF;
    PERFORM dblink_connect_u('mmall','dbname=FFAccount');
    SELECT INTO unit FROM dblink('mmall',
        'SELECT money_unit FROM itemmall WHERE item_id = ' || pItemID::text ||
        ' AND item_group = 6 AND note = ' || quote_literal('{marker}') || ' LIMIT 1',
        false) AS sale(mu smallint);
    PERFORM dblink_disconnect('mmall');
    IF unit IS NULL OR (unit <> 1 AND unit <> 2) THEN
      RAISE EXCEPTION 'req_buy_item: item % is not priced in the F2P item mall', pItemID;
    END IF;
    spend := pBuyPoint * 1000;
    IF unit = 1 THEN
      IF rgold < spend THEN
        RAISE EXCEPTION 'req_buy_item: insufficient gold on % (need % base units)', pChar, spend;
      END IF;
      PERFORM dblink_exec('mchar',
      'UPDATE player_characters SET gold = gold - ' || spend || ' WHERE id = ' || rid || ';');
      afterg := rgold - spend;
      afterb := rbind;
    ELSE
      IF rbind < spend THEN
        RAISE EXCEPTION 'req_buy_item: insufficient bound gold on % (need % base units)', pChar, spend;
      END IF;
      PERFORM dblink_exec('mchar',
      'UPDATE player_characters SET bind_gold = bind_gold - ' || spend || ' WHERE id = ' || rid || ';');
      afterb := rbind - spend;
      afterg := rgold;
    END IF;
    PERFORM dblink_disconnect('mchar');
    INSERT INTO web_itemmall_log (straccountid, strcharid, serverno, itemid, itemcount,
                                  buyprice, clientip, buytype, bonus, buytotal, remain_point)
    VALUES (pAccountID, pCharName, pServerIP, pItemID, pAmount,
            pBuyPoint, pClientIP, pBuyType, 0, pBuyPoint, afterg / 1000);
    RETURN (afterg / 1000, afterb / 1000);
  EXCEPTION WHEN OTHERS THEN
    BEGIN PERFORM dblink_disconnect('mchar'); EXCEPTION WHEN OTHERS THEN NULL; END;
    BEGIN PERFORM dblink_disconnect('mmall'); EXCEPTION WHEN OTHERS THEN NULL; END;
    RAISE;
  END;
END;
$rf$;

COMMIT;
"""

VM_RUNNER = ROOT / 'ops/install-full-mall-inner.py'


def vm(*args):
    result = subprocess.run([sys.executable, str(ROOT / 'ops/vm.py'), *args],
                            capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode:
        raise RuntimeError('vm.py %s failed:\n%s\n%s' % (' '.join(args), result.stdout, result.stderr))
    return result.stdout


def failures(config):
    problems = []
    if config.get('marker') != MARKER or config.get('item_group') != 6:
        problems.append('catalog identity mismatch')
    items = config.get('items') or []
    if not items:
        problems.append('catalog has no items')
    silver = config.get('silver_slots') or []
    if silver != [27]:
        problems.append('silver slots changed: %s' % silver)
    for row in items:
        if not (isinstance(row['id'], int) and 1 <= row['id'] <= 65535
                and row['price'] >= 1 and row['money_unit'] in (1, 2)
                and 1 <= row['detail_type'] <= 43 and row['index'] >= 1):
            problems.append('bad row %s' % row)
            break
    return problems


def relabel(config):
    path = ROOT / 'client/Requiem Aurakingdom/data/db/T_TextIndex.ini'
    original = ROOT / 'private/client-original/T_TextIndex.ini'
    if not original.exists():
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(path.read_bytes())
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    keep = ROOT / 'private/client-original' / ('T_TextIndex.pre-mall-f2p-' + stamp + '.ini')
    keep.write_bytes(path.read_bytes())
    data = path.read_bytes()
    changed = {}
    for slot in sorted(int(k) for k in config['label_ids']):
        ident = str(LABEL_BASE + slot)
        label = config['slots'][str(slot)].encode()
        data, n = __import__('re').subn(rb'(?m)^' + ident.encode() + rb'\|[^\r\n]*',
                                        ident.encode() + b'|' + label + b'|', data)
        if n != 1:
            raise RuntimeError('label %s replaced %d times' % (ident, n))
        changed[ident] = label.decode()
    path.chmod(0o666)
    with path.open('r+b') as stream:
        stream.write(data)
        stream.truncate()
    import hashlib
    return {'changed': changed, 'client_label_sha256': hashlib.sha256(data).hexdigest(),
            'saved_prior_state': str(keep)}


def main():
    if '--yes' not in sys.argv:
        raise SystemExit(__doc__ + '\nDestructive: pass --yes to confirm the item mall wipe.')
    config = json.loads((ROOT / 'docs/mall-f2p-catalog.json').read_text())
    problems = failures(config)
    if problems:
        raise SystemExit('Catalog validation failed: %s' % problems)

    billing = TEMP / 'mall-f2p-billing.sql'
    billing.write_text(BILLING_SQL.format(marker=MARKER), encoding='utf8')
    VM_OPERATIONS_FILES = [
        (ROOT / 'docs/mall-f2p-catalog.json', '/root/mall-f2p-catalog.json'),
        (billing, '/root/mall-f2p-billing.sql'),
        (VM_RUNNER, '/root/install-full-mall.py'),
    ]
    for src, dst in VM_OPERATIONS_FILES:
        vm('put', str(src), dst)
    print('running VM installer ...')
    print(vm('run', 'python3 /root/install-full-mall.py'))

    vm('get', '/root/full-mall-report.json', str(TEMP / 'full-mall-report.json'))
    report = json.loads((TEMP / 'full-mall-report.json').read_text(encoding='utf8'))
    report['relabel'] = relabel(config)
    dest = ROOT / 'docs/mall-f2p-install-report.json'
    dest.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
