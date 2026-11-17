Zrymund's Astral Sovereign upgrade — 25 October 2026

Installed and verified in the running server:

- Equipment requires internal level 130, displayed SLv30. The cap is internal 150, displayed SLv50. The native level vectors contain 150 entries and the active level switch is 150. Leveling and combat at the new cap still require gameplay testing.
- Zrymund remains internal 120 / SLv20. All 11 custom equipped instances were moved intact to inventory bag index 8, slots 1–11 (the last bag). No item enhancement, quality or instance identifiers were changed. Use `/set_level 130` in game if you want to advance to SLv30 and equip the set; `/set_level 150` targets SLv50.
- Whip template: 3,000,000 attack. Each other piece: 500,000 attack. Every piece: 250,000 CRIT/SPD/EVA, 500,000 DEF, 5,000,000 HP except the chest's 20,000,000 HP. Ordinary percentage caps remain unless a supported cap bonus is included.
- Whip: PEN +999%, Armor Piercing +500, damage +300%, every elemental damage +300%, damage received -90%, physical/magical life steal 100%, CRIT DMG +500%, maximum CRIT DMG +100%, Move SPD +150%.
- Ten other pieces each have a distinct passive ID granting PEN +100% and Armor Piercing +100. This avoids relying on repeated copies of one buff stacking.
- Armor: 2 pieces grant Max HP +50%; 5 pieces grant PEN +200%, Armor Piercing +200 and maximum CRIT DMG +50%.
- Cloak/necklace/ring: 3 pieces grant damage +50%, CRIT DMG +200%, maximum CRIT DMG +50% and Armor Piercing +300.
- Trophy pair: PEN +200%, Armor Piercing +300 and healing potency +100%.
- Nominal full-set contributions: PEN +2,399%, Armor Piercing +2,300. Other character bonuses are additional. PEN offsets enemy toughness; it is not an unlimited damage multiplier.
- Native Armor Piercing is opcode 2155 with the amount in its first exposed parameter. The initial defensive-armor parameter was corrected before gameplay. All 18 effect definitions were checked as actual parsed server commands; set bonus references were verified against native hidden item templates.
- Negative allocated-point balances were refunded: 121 attack and 120 defense points remain available, with the six old allocations reset to zero.
- Quest tables were hashed before and after the primary update and remained identical. Character level, EXP and currency also remained identical. The later cleanup changes only title unlocks: 2,463 unnamed placeholders removed; 28 valid translated titles restored.

Client text repairs preserve existing English names. Missing names use an unambiguous existing English alias when available, otherwise the matching native V15 Chinese name. Blank unused definitions receive an explicit unused label. Missing-name repair counts are recorded in sovereign-v2-manifest.json. Four joined enchant records and 48 missing mall record terminators were normalized. Some inherited malformed mall text and unsupported client content remain; this is not a complete clean-client rebuild.

The attempted broad server-side translation synchronization failed the server's native data-loading check. All seven server T_*.ini files were restored from the known-working backup; the client text repairs remain installed. Do not rerun finish-sovereign-v2.py or repair-server-text-schema.py as a deployment. Native server-sent missing names remain a known limitation until individual table loading is resolved. Full English restoration still requires the matching clean V15 archive, currently unavailable due to MEGA quota.

Backups:

- VM primary update: /var/backups/aurakingdom/pre-sovereign-v2-20261025T053959Z
- VM AP/title update: /var/backups/aurakingdom/pre-sovereign-v2-final-20261025T054707Z
- Windows client backups: private/client-original/sovereign-v2-* and text-schema-*.
- The final backup's server T_*.ini files are the active known-working server translations. S_Item/S_Enchant from that backup precede the final AP correction; restoring those also requires restoring matching client definitions.

All six services were running after final verification. In-game equip, combat, set tooltips, client naming and SLv50 behavior await the player's test. Launch the usual client/Requiem Aurakingdom/Game.exe. The separate clean-client folder remains incomplete.

playerone's requested password change was verified in FFMember, FFAccount and the GM-tool account. The current password is saved in private/game-accounts.json; it is deliberately omitted here.

Startup recovery, same day: the player reported exit before login. Restored all seven client T_* tables from the pre-upgrade baseline, overlaying only ASCII custom item, enchant and set records. The broad missing-name repairs and record normalizations described above are now rolled back on the client as well. The gear templates, independent effects, level cap and character changes remain. After relaunch, Computer Use visually confirmed Zrymund's character-selection screen. Character-to-map loading and combat remain to be tested by the player. The inherited Err names remain unresolved. Details and the recovery backup path are in client-startup-recovery.json. Do not redeploy the earlier broad translation payloads.

SLv50 boundary repair: the player confirmed SLv49 works but SLv50 crashes. The client minidump records access violation 0xc0000005 at game.bin 0x808215, reading address 0x8 with EAX=0. Disassembly shows the EXP display increments the current level and calls the level-data getter before reading the next level's EXP. At internal 150 it requests missing row 151. Added row 151 to C_Level and S_Level as a reference row copied from row 150; the playable cap and parameter-22 vector size remain 150. This does not grant an SLv51 cap. Native row 151 and the original 150-entry EXP vectors were verified. Zrymund was recovered from internal 150 to 149 (SLv49), with all other character fields and all quest, inventory, equipment and point-table hashes unchanged. A player retry of `/set_level 150` is required to verify the repaired client behavior.

Damage reflection: the Sovereign whip now additionally grants enchant 180020, Sovereign Retribution. Opcode 2037 with parameters [100,100] loads as CEC_DamageRebound with Probability=100, ReboundRate=100 and damage-type mask 15. It reflects damage taken; it does not remove the incoming hit. Existing gear instances inherit the passive from their template. See slv50-reflect-native.json and slv50-reflect-report.json for verification and backups. Reflection in actual combat remains a gameplay check.

Player acceptance, 25 October 2026 (Asia/Jakarta): after the reference-row repair, the player explicitly confirmed “SLv50 works now” when retrying `/set_level 150`. The previously failing SLv49-to-SLv50 transition is now gameplay verified. This confirmation does not establish full coverage of every SLv50 system or reflection in combat.
