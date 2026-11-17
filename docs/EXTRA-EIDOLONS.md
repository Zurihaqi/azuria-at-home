# Additional Eidolon port — 31 October 2026

Deployed 33 client-defined companions into the normal V15 server, then added
them to playerone's account storage for Zrymund. Total collection: 183 playable
templates, with four existing active slots and 179 stored companions.

New companions have level 99, four stars, affection 10, energy 100, maximum
native emblem growth and the maximum strengthening rank supported by each
skill's actual tier list. Existing 150 records are unchanged, including active
slots, equipment, names, skins and pending link gifts. The full character row,
inventory, 13 quest-related tables and other accounts' Eidolons were verified
unchanged before services restarted.

## Data and compatibility

The port appends partner, spell, effect, evolution, dialogue, mission, gift,
key and fragment recipe definitions from the installed client, preserving all
existing server records and custom gear. There are 528 additional spell records
and 1,059 effect dependencies. Existing client models and animation controllers
were located for all 33 companions. No production executable was patched.

One unsupported effect command (2062) was represented using the existing native
2046 element-damage vector, matching an established +10% damage against Lightning
effect. New link gifts use compatible reconstructed distributions rather than
verified retail loot. Fragment recipes consume ten matching fragments, twenty
Medium Eidolon EXP Crystals and 5,000 native currency units to produce a key.

Companion display labels include authored English names. Some new skill names
and descriptions retain Chinese text; this is not a complete official English
localization. Appended translation strings use UTF-8 to avoid delimiter corruption
from CP950 trail bytes; all pre-existing translation bytes remain unchanged.

Startup correction: the Windows client exited before login with the newly added
non-ASCII effect translations. Replacing only those 120 added translations with
ASCII-safe labels allowed startup through character selection. These effects
temporarily display generic English labels and omit unverified Chinese tooltip
text. Their IDs, gameplay definitions, server records and existing translations
are retained. The client payload and preparation script include the correction.

## Verification and limits

The isolated native server loaded the additions and an ordinary test character
received and decoded four new active companions. A complete 33-companion bank,
summon and combat test was not completed before deployment, at the user's request
to deploy. Normal production services loaded and all six processes and game
listeners came online. In-game rendering, storage retrieval, summoning and each
new skill still require player verification. Report any problematic companion
by name; do not treat this as full official-server compatibility.

Reopen the usual Game.exe, load Zrymund, open Eidolon management and move a new
companion (for example Aurora) from storage into an active slot, then summon it.
The supported Eidolon cap remains 99; player Super Levels do not raise it.

## Backups and recovery

Server backup: `/var/backups/aurakingdom/extra-eidolons-20261031T111411Z`.
It contains the full pre-change FFDB1 dump, original changed tables, account
collection snapshot, exact grant SQL, created-record list and verification report.

Client backup: `private/client-original/extra-eidolons-20261031T111347Z`.
Changed client files: C_ItemMall.ini, C_Combine.ini, T_Enchant.ini, T_Item.ini.

For rollback, first log out humans and stop all game services and bots. Remove
only the 33 IDs listed in created.json for account 2419, restore the backed-up
server tables and corresponding client files, then restart services. Review
subsequent changes before reverting tables. Do not restore the entire database
just to remove these companions, because that would discard later progression.

Machine-readable reports: extra-eidolons-report.json and
extra-eidolons-client-report.json. Deployment scripts: ops/deploy-extra-eidolons.py
and ops/deploy-extra-eidolons-client.py. Both reject changed source hashes; the
server script rejects active humans and rolls back additions on failure.
