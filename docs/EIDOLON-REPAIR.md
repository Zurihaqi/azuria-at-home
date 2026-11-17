# Eidolon links and skill costs — 31 October 2026

## Link gifts

The active S_Partner table referenced 37 absent S_DropItem records: 10114–10150.
This affected partners 7 and 209–244, including Zrymund's Gaia (232), Zhang Fei
(239), and Odin (240). Native GetLinkGift returned false before generating any
items, so the native claim handler retained `link_time=-1` (gift pending).

Added the missing records using the existing native link reward distribution.
The newer entries use the last existing gift's probability schedule, each
partner's existing key fragment, shared XP crystals/emblem chest, generic
Eidolon card pack, and a matching statue where identifiable. Otherwise the
statue slot uses the existing large XP crystal. Starter partner 7 uses its
existing personal evolution material and the starter distribution. Partner
244's key fragment is itself absent from this release, so its rare slot uses
the existing Hero Emblem. These are compatible reconstructed distributions,
not recovered retail-original reward tables. Existing gift rows are unchanged.

All referenced item IDs exist in the live S_Item/S_ItemMall tables; primary
reward probabilities sum to 100. All configured partner gift IDs now resolve.
No character rows, link timers, inventory, or quest records were edited.

## Free skill upgrades

ZoneServer CheckSpellUpgradeItem still validates the partner, skill slot,
current rank, supported spell tiers, configured maximum and next-level record.
At 0x497753, only its fragment-cost load is replaced by a zero value. The
native function returns cost zero; EudemonSpellUpgrade's existing zero-cost
guards skip both fragment deductions, then perform the ordinary upgrade.

Eight actual x86-64 function emulation cases passed: zero and positive owned
fragment balances, multiple slots, final allowed upgrade, negative current
rank, over-cap ranks and invalid slot. Original level tables remain intact
because their positive cost rows also establish the build's native skill cap.

Client cost text is not modified. It may display the original requirement;
whether the client independently blocks an upgrade without fragments needs a
gameplay test. Server-side upgrades consume no fragments, even when owned.

## Deployment and recovery

Backup: `/var/backups/aurakingdom/eidolon-repair-20261031T083502Z` contains the
original ZoneServer, S_DropItem.ini, and FFDB1 dump. See
`eidolon-repair-report.json`. Bots were stopped before the server restart;
their repeated-death pause needs the separate recovery/restocking work.

To roll back these changes, log humans out, stop bots and `aurakingdom`, restore
only the backed-up ZoneServer and S_DropItem.ini, and start `aurakingdom`.
There is no need to restore the database for this file-only change. Do not use
this old binary backup after later binary changes without reviewing those changes.

Gameplay acceptance still pending: receive one already-completed link gift,
verify it reaches inventory and clears the pending state; upgrade an eligible
Eidolon skill and verify its level increases with unchanged fragment counts.
