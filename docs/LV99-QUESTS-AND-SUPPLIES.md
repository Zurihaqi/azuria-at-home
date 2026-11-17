# Zrymund's level-99 quest completion and new mall supplies

Applied 2026-10-25. Database backup: `/var/backups/aurakingdom/pre-lv99-supplies-20261025T042557Z/`.

Zrymund remains level 99, with **1,002,435,749 EXP** (one below the live native threshold of 1,002,435,750). The client had six changed EXP rows, including a level-100 threshold of 8,002,435,750. C_Level.ini EXP columns 1 and 33 were aligned to the running server so the bar displays correctly. No other level-table fields were changed.

## Quest coverage

The user explicitly requested quest completion, superseding earlier instructions to preserve progression. After a separate choice, Awakening remains pending so the character does not advance to SLv.1.

- 1,245 main-story records, 59 side-story records, 10 adventure stories and 9 housing/ranch quests now have native completed state 1: **1,323 total**, including **1,273 newly completed** records.
- Selected titled quests are Lv.1–99. The ten adventure stories have native level-70 conditions. Daily/repeatable/event commissions, SLv quests, unused/undefined records and character boost quests were excluded.
- Quest **2523** (final Awakening) has accepted state 3 and a tracker entry. Quest 2524 and subsequent post-Awakening progression were not completed. An interrupted Awakening instance can require returning to its NPC/Emma to resume.
- Subweapon, card, player-room and ranch feature bits are set (state_flags 15). The Awakening bit is clear. Native SetStateFlags uses `1 << enum`; Awakening is enum 4 and its normal command advances to the next level.
- Only selected three-bit FMS entries, their one-time completion counters, tracker entries, EXP and the corresponding character feature flags were changed. Other quest bits, level, gold, inventory, equipment, mastery records and character fields were preserved and checked.
- This is an administrative progression skip. Ordinary quest item rewards and item-choice rewards were **not** retroactively delivered, and scripted encounters/cinematics were not replayed. The database records were verified; the user's in-game check remains pending.

## New stock categories

All new listings cost **1 AP**, contain one item per purchase and use sale price 0. Existing shop listings and the previous gear/catalog enhancement hook were untouched.

| Location under Item Mall → AP | New items |
| --- | ---: |
| Eidolons → Eidolons | 148 EXP crystals, crests, purification/evolution supplies and compatible Eidolon accessories |
| Costumes → Enchantment Cards | 471 compatible enchantment cards |
| Gear Improvement → Fortification | 103 fortification scroll variants |
| Gear Improvement → Other | 653 materials, refining/weapon/armor cores, recipes and forging supplies |

The server's live WorldServer cache was checked: all **1,375** added listings loaded in groups 102/103/105 with the expected subcategories and prices. Test, undefined, reserved, occupied and region-only voucher names were filtered out; quest-item types were not selected. Compatibility checks required matching server/client item IDs, native types and icon/model references.

These are existing menu categories. Some items have their own level/system prerequisites. Real purchases and use of the supplies still need gameplay verification. Manifest: `lv99-supplies-manifest.json`; deployment: `lv99-supplies-report.json`; runtime cache: `supplies-cache-report.json`.

## Client reset status

The supplied V15 archive's executable is version 15.0.1.16. Its 2,870 objective definitions match S_Mission.ini, whereas the Requiem client differed on 1,152 objective definitions. Original C_Mission.ini and T_Mission.ini were recovered and their sizes/ZIP CRCs verified, then installed in the current client with backups. Requiem's own release description advertises one-mob/item quests, explaining the observed mismatch with the stock server rules.

The **full clean reset is incomplete** because MEGA returned HTTP 509 (bandwidth exceeded). The separate `client/Aura Kingdom V15 Clean` directory must not be used yet. The active shortcut and current client remain in place, including custom item definitions needed for existing gear. The original V15 release may itself contain older community branding; it is the matching release baseline, not a claim of pristine official provenance.

The official 2023 installer previously used for music contains a V17 executable (17.0.1.8), so it was not used to replace the working V15 game. No verified public V17 server package was found in the current searches; forum version claims are not installation evidence.
