# Zrymund Guitar conversion — 31 October 2026

Guitar is now the main weapon class (mask 32768, class 16); Whip remains the
subclass (131072). `class_id=0` is the existing generic character field and was
not incorrectly treated as the weapon class. The actual class pair lives in
`player_weapon_type`.

All 49 Guitar Envoy abilities and 160 compatible Guitar/common skill-mastery
tier entries are learned. The six selected mastery slots use compatible gold
tiers; the Whip-specific slots were replaced by Guitar IDs 50136 and 50148.
Both weapon-specialization branches are level 70, the previously verified cap.
Guitar's existing active combat skills were already saved at character level
150; the conversion preserves those records.

The new item is **Zrymund's Astral Sovereign - Worldshatter Guitar**, template
61604, in inventory bag 9, slot 13 (database bag 8, location 12). It is +30 and
five stars and requires SLv30. It inherits the custom Whip's 3,000,000 base DMG,
other extreme base stats, and passives 180001/180002/180004/180020, including
PEN, Armor Piercing, life steal, movement/critical bonuses and damage reflection.
Its Guitar model, weapon category and fortification metadata come from the
matching native Guitar template 33915. The custom Whip remains intact.

The previously equipped ordinary Guitar was moved from secondary weapon slot 6
to the empty main slot 5; the requested new custom Guitar is left in inventory
for the owner to equip. No item instance was overwritten or deleted.

The game service was stopped for a full database backup and offline edits.
Quest-table fingerprints and the entire unrelated character row were verified
unchanged, including level, EXP and currency. Inventory instance ID allocation
occurred while the native allocators were stopped, before cold startup scans
persisted IDs. The new item was verified present with +30/five-star fields.

Server backup: `/var/backups/aurakingdom/guitar-switch-20261031T052426Z`.
Client backup: `private/client-original/guitar-switch-20261031T052316Z`.
Exact counts, selections and inventory placement: `guitar-switch-report.json`.
Prepared template hashes and definitions: `guitar-switch-prepared.json`.

All six native game processes and both bots were running after deployment.
Client/server item definitions and offline character records are verified;
character loading, rendered mastery/Envoy UI and Guitar combat effects still
need the owner's in-game check. Open the usual Play shortcut and equip the new
Guitar from the last bag.
