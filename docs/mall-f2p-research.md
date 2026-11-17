# F2P item mall — billing research + rebuild plan

Status: research locked 2026-10-28. Prior caution still applies: mall purchases were never gameplay-tested before; validate in-game after deployment.

## 1. How mall billing actually works (reverse-engineered)

### Purchase path
1. Client sends buy request → WorldServer `lapis::CNE_CW_ServerItemMallReqBuyItem::Execute` (0x538480, 9,269 bytes, `.symtab` intact).
2. The client command carries an explicit wallet field. Disassembly proves **buy_type is client-chosen**, not derived from the DB row:
   - `0053916c cmp word [rbx+0xc], 0 / jle → set 1` — buy_type defaults to 1 when client sends ≤0.
   - Gate at 0x5391e2: event field `[rsp+0x48]+4` must equal 1 for group‑1/2 wallet items (valid pvalues wallet item), else error.
3. Item + price come from `FFAccount.itemmall` row (field at `data+0x40` in the SItemMallItem struct loaded from DB): total cost = unit price × amount; special_price is honored (0x5397c4 branch picks stored field +8 when special active).
4. Purchase executes via `CAccountDBO::ItemMallReqBuyItem` (0x4ca200) → GatewayServer → FFMember SQL:
   - `SELECT req_buy_item('<account>','<serverip>',<item_id>,'<charname>',<buy_point>,'<clientip>',<buy_type>,<amount>)` — 8 args, sole string ref `0x81a4d48`, call at `0x804d4c4`.
   - Enclosing gateway function prologue at `0x804d380` (stack 0x46c). Vararg order at the call (from `0x804d46e–0x804d4c8`):
     `[ebp−0x442]` (short, buy_type) → `[ebp−0x440]` (short, amount) → `[ebp+0x20]` (buy_point, long) → `[ebp+0x1c]` (charname string) → `[ebp+0x10]` (account) → `[ebp+0x14]` deref (serverip) → `[ebp−0x43e]` (item_id) → `[ebp+0x24]` deref (clientip) — matches the `%s %s %hu %s %ld %s %hd %hd` format.
5. `req_buy_item(plpgsql, FFMember)` loads `pvalues, bonus` from `tb_user`, per buy_type:
   - type 1: `pvalues −= buy_point`, `bonus += buy_point/5` (5% bonus kickback) → returns `(pvalues, bonus)`.
   - type 2: same flow against `bonus`.
   - Logs to `web_itemmall_log`; gateway logs "point:%d bonus:%d, type=%hd".
   - No binary patch needed: we rewrite this plpgsql (and `get_point_info`) in FFMember to bill `player_characters.gold` / `bind_gold` in FFDB1 (dblink/`dblink_exec` or direct FDH is available; FFDB1 is on the same cluster).

### Wallet identity (maps 1:1 to in-game currencies)
- `CNC_CW_ClientItemMallPointInfo::Serialize` (0x513420) writes **exactly two ints** `[rdi+8]`, `[rdi+0xc]` → the mall UI's two balance slots. Perfect slots for **gold** (replacing pvalues) and **bind_gold** (replacing bonus).
- `get_point_info('<account>')` feeds those two ints → rewrite to return the account's active character `gold, bind_gold` from FFDB1.
- `FFAccount.itemmall.money_unit` observed live values 0/1/2/3; wallet match: 1 = first wallet (gold), 2 = second (bind gold). Use `money_unit=1` for gold-priced rows and `mount_unit=2` for silver rows; `point` column = unit price in that wallet's base unit. 1 gold = 1,000 base units, so a 5 gold price = `point=5000`? **verify** against prior working rows: old catalog used `point=1` with money_unit=1 and purchases were rejected in earlier testing as unpriced — set explicit scaled values and confirm the display/popup during the in-game test.
- Response/error event: `CNC_CW_ClientItemMallReqBuyItem::Serialize` at 0x50ffe0 writes a 16-bit event code plus the standard event payload; error text ids all route to `TexOutputIndex` events ("CNE_CW_ServerItemMallReqBuyItem> ...") — client treats insufficient funds as generic error popup, no extra patching needed.

## 2. Live DB state (before wipe)
- `FFAccount.itemmall`: 13,924 rows, groups/units:
  1:15/1, 2:619 (1/2/3 mixed), 3:304, 4:52, 5:850, 6:10,627 (all money_unit=1 — prior gear catalog), 8:2,485, 47:13, 48:13, 49:42, 51:3, 52:3, 62:50 (unit 0), 99:12.
- All of it gets deleted; new catalog is group 6 only, money_unit 1 (gold) or 2 (bind gold).

## 3. Rebuild design
### Categories (≤43 label slots, reuse ids 61001–61043)
`T_TextIndex.ini` ids 61001–61043 currently hold weapon/armor/costume names from the gear catalog relabel. Final list = one slot per distinct category bucket produced by the generator (weapons 7–24 keep their names; armor 1–6/31–36; accessories; consumables; enchant cards; key fragments; cores; mounts; fashion/costume; fishing; cooking; eidolon keys; etc.). Labels rewritten in place, count must stay ≤43 or slots get merged.

### Price curve (approved)
Price = category base × level band × quality/rare factor, rounded into ≥1 gold. Enforced floor 1 (gold wallet row) or 1 (silver wallet row). Maximum sanity cap: no row above ~10,000 gold.

### Wallet split
- `money_unit=1` → billed from character **gold** (rewritten req_buy_item type 1 branch).
- `money_unit=2` → billed from character **bind_gold** (type 2 branch) — the "silver" wallet.
- Assignment policy (default, tunable before deploy): consumables/common materials → silver; everything else → gold.

## 4. Open items
- Confirm display-price source in client popup during in-game test (likely C_ItemMall.ini cached data); DB `point` is the authoritative debit.
- Dashboard sales state in `private/dashboard/dashboard.sqlite` referencing the wiped catalog must be cleared during deployment.
- Backup target: `/var/backups/aurakingdom/pre-full-mall-<stamp>` (pg_dump all three DBs) + local copy of `T_TextIndex.ini` before relabel.
