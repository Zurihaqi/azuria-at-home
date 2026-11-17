# F2P item mall — deployment plan (approved)

Marker for the rebuild: `codex:mall-f2p:v1`. Backed by `docs/mall-f2p-research.md`.

## What changes
1. **Wipe**: every `FFAccount.itemmall` row (13,924) is deleted.
2. **New catalog**: every purchasable non-debug item from `S_Item.ini` ∪ `S_ItemMall.ini` that the client can display (C-side match, id ≤ 65,535, non-empty title, debug/dev/GM name filter) — ~20k+ items across all type ids — inserted into group 6 with per-item `point` price ≥ 1.
3. **Wallet per item (server-enforced)**: `money_unit` 1 = gold wallet, 2 = silver (bind gold). The rewritten `req_buy_item` debits `player_characters.gold` (type 1 route) or `bind_gold` (type 2 route) — for enforced rows it charges the row's wallet regardless of the client's chosen type, which kills both client-choice mismatch and free-item exploits (unknown/absent mall item_id ⇒ hard error, purchase refused).
4. **Billing rewrite** (FFMember, plpgsql only — no binary changes anywhere):
   - `get_point_info(account)` → returns the account's most-recently-saved character's `(gold/1000, bind_gold/1000)` — mall UI then displays real gold totals. Verified: `CNC_CW_ClientItemMallPointInfo::Serialize` writes exactly two ints.
   - `req_buy_item` 8-arg function rewritten: resolves `player_characters` by charname + account (`deleted_time`=0), validates item exists in `itemmall` (via dblink), debits 1 gold per point for the item's wallet, keeps `web_itemmall_log` audit, returns `(gold, bind_gold)` in the same record shape the gateway already consumes.
   - Older `req_buy_item` overloads and `get_point_info` dropped/rewritten, mirroring FFMember.bak definitions.
5. **Labels**: `T_TextIndex.ini` ids 61001–61043 relabeled in place (local file edit + push); ≤ 43 slots so no binary patch. Slots 1–18 (weapon types 7–24) and 19–24 (armor types 1–6) keep verified names; slots 25–43 are remapped:
   25 Mounts · 26 Pets & Hatchlings · 27 Consumables (silver) · 28 Materials · 29 Secret Stones · 30 Enchant & Fortification · 31 Eidolon Keys · 32 Eidolon Treasures · 33 Duel Cards · 34 Crafting Recipes · 35 Cores · 36 Legendary Gear Bags · 37 Crates & Bags · 38 Furniture & Garden · 39 Fashion, Gifts & Wings · 40 Head Costumes · 41 Body Costumes · 42 Prize Gear · 43 Fishing & Cooking Gear
6. **Dashboard**: clear sales state in `private/dashboard/dashboard.sqlite` referencing the old catalog.
7. **Backups**: `/var/backups/aurakingdom/pre-full-mall-<stamp>` — pg_dump FFAccount + FFDB1 + FFMember + full `itemmall` JSON snapshot + local `T_TextIndex.ini` copy before relabel.

## Pricing (approved curve; prices in gold, ≥ 1)
`price = base(category) × level band (1 + required_level/25) × rarity factor (keyword-based)`, rounded, floor 1, cap 10,000 — landed samples: HP potions ~1–20, lvl-50 gear ~30, lvl-100+ legendary gear 300–1,000, mounts 50–500, Eidolon keys 100–1,000, prize gear up to ~5,000.
- Daily/cons consumables slot is silver-priced (charged from `bind_gold`).

## Deployment order (mirror of prior migrations)
1. offline-characters check (same `quit=0` gate), full backups, stop `aurakingdom`
2. SQL transaction: delete all `itemmall`, drop+recreate FFMember functions, insert new rows
3. push relabeled `T_TextIndex.ini` to `client/Requiem Aurakingdom/data/db/`
4. clear dashboard sales state
5. restart, verify counts + note marker + wallet split, in-game test (display / price popup / purchase from gold wallet / purchase from silver wallet / insufficient funds message)

## Not claimed until played
Mall display, price popup, purchase, and wallet debits were verified statically only; gameplay test by the user is the acceptance gate (STATUS.md caution holds).
