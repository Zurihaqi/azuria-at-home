# Quest 1017 investigation — 31 October 2026

## Catch-up

Both bots are running in the normal world. Recent work added a scene actor/map
index, ordinary portal travel, potential-point spending, hostile grind selection,
death-aware quest retry budgets, and dashboard start/stop operations. ML remains
recording/shadow mode; its holdout gate has not passed. This is not an ML-driven
quest solver.

## Confirmed failure chain

1. The four mound fragments (item 30301) are collected. Fresh native inventory
   snapshots show 4/4 for both bots. The old stack-count bug is repaired.
2. The second objective requires item 30635 from Keda, template 41165, on map 622.
   Both bots can use the ordinary portal, reach him and attack him. Historical
   attempt journals show repeated native deaths to that exact template.
3. The deployed potential-point code deliberately filtered page 0, so only
   attack points were spent. A defense-page change existed locally but had not
   reached the VM. New live snapshots confirmed Awan's 2 and Arden's 1 available
   defense points were spent; both pages now have zero free points.
4. A single rejected or unconfirmed skill cast disabled the skill for the entire
   session. Both allowlisted attacks were disabled in the original live status.
   Temporary failures now use bounded backoff and retry; unrelated command errors
   cannot reject the pending skill. Fresh native acknowledgements confirm casts.
5. Each bot owned ten Tiny HP Potions (10534) but had no recovery action. The new
   action uses only owned potions and confirms stack consumption in a fresh native
   inventory snapshot. Enchant 35001 restores 50 HP/s for 10 seconds; attempts are
   spaced at least 15 seconds apart. The trigger uses current native HP and the
   highest observed HP, which is explicitly not a decoded maximum-HP field.
6. Once healing kept them alive, the objective timed out after 90 seconds. The
   encounter driver was limited to 60 seconds. Budgets now nest correctly:
   180-second quest encounter, 240-second combat objective, 600-second quest slice.
   Attack backoff from an old actor no longer forces a new encounter to start at
   the six-second maximum interval.

## Deployment and validation

- 95 targeted tests passed under the VM's Python 3.9, covering battle, potential
  allocation, combat, collection objectives and quest execution.
- First bot-only backup: `/var/backups/ak-bots/quest1017-20261031T044255Z`.
- Combat-budget follow-up: `/var/backups/ak-bots/quest1017-20261031T044747Z`.
- The native game service stayed running. No character/progression SQL writes,
  GM commands, generated gear or administrative quest completion were used.
- Native point allocation, skill acceptance and owned potion consumption were
  observed live.
- Both bots subsequently completed quest 1017 through native loot and turn-in:
  Awan's journal recorded `finished/confirmed` at Unix time 1793422243.45254,
  Arden's at 1793422275.0320075. Their boss objectives took about 100 and 131
  seconds respectively, which explains why the old 90-second wrapper failed.
- Ground-warning avoidance is separate follow-up work; see `BOSS-AVOIDANCE.md`.

## Remaining boundaries

Both still wear their original level-1 weapon and starter armor. The owned-gear
selector finds no upgrades in their bags; vendor purchasing and repair are not
implemented. Recovery supplies are finite. The bot should eventually buy those
through ordinary shop actions rather than grant itself items. These changes do
not establish broad quest or dungeon coverage.
