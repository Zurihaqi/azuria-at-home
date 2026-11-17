# Free Preview / Fitting Room — 31 October 2026

All 1,413 `FFAccount.dressroom` entries now have price zero and deliver the
previewed item directly (`fortune_item_id=item_id`), including formerly
preview-only entries. The catalog's category, ordering, default colors and
location restrictions are preserved. This covers its costume, weapon-appearance
and mount categories. It does not change ordinary item-mall prices.

The native server originally rejected zero prices and its voucher-debit routine
also rejected a zero debit. A 30-byte targeted change enables a free-delivery
branch after the normal free-bag-slot check. Negative prices remain invalid;
positive-price purchases retain the native balance and debit path. No voucher
balance or character currency is granted or changed.

Ten Unicorn emulation cases passed: zero balance, positive balance, multiple
quantity, full bag, negative price, paid purchase/debit and insufficient funds.
The entire database and original executable were backed up before deployment.
The binary's existing mall/debit/enhancement hooks were preserved; the new stub
uses verified zero padding in their mapped executable segment.

Backup: `/var/backups/aurakingdom/free-preview-20261031T060557Z`.
Patch bytes/tests: `free-preview-patch.json`.
Deployment report: `free-preview-report.json`.

All six native game services were running after deployment. The owner's check
showed both purchase sections still displayed "Product not available."

## Client availability correction

The active `game.bin` voucher-panel function at `0xd50080` explicitly hid the
purchase controls for `price <= 0`, independently of the server's delivery code.
At `0xd500cd`, the six-byte conditional branch now rejects only `price < 0`.
The preceding nonzero-item-ID check, item-template lookup, native confirmation
dialog and native purchase packet remain intact. The AP purchase path is unchanged;
use the **Fantasy Gift Vouchers** section for free purchases.

Eight native x86 guard emulation cases passed, including zero, positive and
negative prices and missing item IDs. Two original-build cases reproduced the
zero-price rejection and normal positive-price availability. The complete client
executable was backed up under `private/client-original/free-preview-20261031T080426Z`.
See `free-preview-client-report.json` and `ops/fix-free-preview-client.py`.

The patch is installed. Reopen the usual game, select a Preview item and check
the voucher section displays price 0 and a Buy button. One actual gameplay
purchase and unchanged voucher balance still need owner verification; machine-code
emulation is not an end-to-end gameplay purchase test.
