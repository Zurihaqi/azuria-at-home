# Zrymund account collection — 31 October 2026

Account 2419 (`playerone`), character 50000001 (Zrymund), now owns all 150
playable Eidolon templates present in both installed server and client data.
Template 1 is the tutorial-only Valkyrie and is excluded. Client-only templates
without matching server definitions are excluded.

136 records were added and 14 existing records upgraded. Four equipped
companions retain their IDs, slots and equipment: starter fox template 6,
Gaia 232, Zhang Fei 239, and Odin 240. (Template IDs are authoritative; display
names depend on the client translation.) The account storage has 146 entries.
Storage is the native `elf.type=1` collection, which the normal AddElf code
expands dynamically; this is not a larger active-summon limit.

Every record has:

- Level 99, the template's native level limit.
- Four stars, the normal evolution path's maximum. The low-level setter also
  accepts a future fifth value, but the native evolution flow supports four.
- Affection level 10 (live S_Parameter 411); capped affection EXP is zero,
  matching the native GainLoveExp behavior at the cap.
- Energy/loyalty 100, full HP and zero residual level EXP.
- Maximum emblem growth: damage 3000, crit 1000, speed/recovery 1000, HP 5000,
  defense 1000, evasion 1000 (live S_Parameter 173–178).
- Maximum supported skill strengthening for each of its three slots. Slots
  with six skill tiers use rank 50; a slot with a single tier retains rank 0,
  meaning its base skill has no strengthening tiers. All referenced skill IDs
  exist in both installed spell tables. No artificial rank is assigned to a
  non-upgradable skill.

Existing equipment, names, skins, missions, pending link gifts, and random
star-bonus reroll selections were preserved. New records use ordinary default
equipment/skin/buff values; no custom accessories or invented reroll effects
were granted. Default star effects and derived combat stats come from native
templates when the game loads the collection. This does not complete Eidolon
dialogue/story quests or grant player cooperative spells administratively.

## Validation and backup

The real native GetMaxHP function was emulated against all 150 prepared growth
profiles. The offline database transaction was checked for every requested
field, unique IDs and storage slots, preserved equipped slots, and exactly one
record per playable template. Zrymund's full character row and inventory were
unchanged, 13 mission/quest-related tables matched their previous hashes, and
other accounts' Eidolons were unchanged. All six native services started.

Backup: `/var/backups/aurakingdom/max-eidolons-20261031T092525Z` contains a full
FFDB1 dump, original/updated collection JSON, created-ID list, manifest and
exact SQL. Report: `max-eidolons-report.json`.

Gameplay validation is pending: open the Eidolon collection, inspect levels,
stars, affection and skills, then move one new Eidolon into the active roster
and summon it. A stopped-service targeted rollback can delete only IDs in
`created.json` and restore only account 2419's original Eidolon records from
`elf-before.json`; retain subsequent player changes when constructing rollback.
Do not restore the entire database merely to undo this collection grant.
