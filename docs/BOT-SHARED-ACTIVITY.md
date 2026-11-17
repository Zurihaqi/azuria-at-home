# Shared questing, hunting, party assistance and local chat

Implemented 28 October 2026 for Awan and Arden, through ordinary player packets.
No production database edits or game-service restart are required.

## Priorities

Both continuous normal-world profiles use the same activity controller. While
solo, they attempt supported quests for up to three minutes, hunt temporarily
for up to three minutes, then retry quests after a short rest. Quest state is
always confirmed by the native server. An unsupported objective remains active;
it is never marked complete administratively.

Joining a party cancels the solo activity, closes NPC/shop interactions, and
switches to following. After leaving the party, solo activity resumes. The
controller serializes movement, dialogue and combat rather than running a
quest driver and companion driver concurrently.

Independent hunting remains limited to the curated ordinary Port Skandia mobs.
It chooses the highest authored enemy level at or below the bot's current level
(the level-3 starter enemies are allowed at levels 1–2). It excludes types for
two minutes after failed fights and five minutes after being killed by them.
It still pauses after repeated deaths. This is a level-based heuristic; it does
not yet estimate survivability from current HP, healing or upgraded equipment.

## Party assist

The bot reacts to the current leader's observed melee or verified single-target
spell messages, and can attack first when the leader selects a monster without
attacking. It polls the native target-of-target request once per second. The
9-byte response is correlated with a single fresh leader query; replies after
leadership/map changes or without an outstanding query are ignored. Request
Deserialize/Execute were checked at `0x750420` / `0x750190`, and response Serialize
at `0x677710`. A target must be alive, visible and classified as an ordinary
hostile in the installed biology table; it cannot be a party member. Leader,
target and companion must be on the same map and within the bounded 30-unit
assist area. Attack intent expires after eight seconds. Target death, loss of
visibility, leadership changes and leaving range invalidate assistance.

The companion walks into melee range and uses normal target-selection and melee
packets. It checks eligibility before each send, retries movement conservatively,
and returns to following after a bounded fight. Party-assisted fights are not
recorded as solo learning examples. This implementation does not enable combat
skills, healing, tanking or dungeon mechanics. Instant human kills may finish
before the bot can reach or hit the monster. EXP eligibility remains a native
server decision; party assist alone is not proof of an EXP-sharing fix.

## Sleeping workers

The native item-use message layout was checked against ZoneServer Deserialize
at `0x7591b0` and Execute at `0x758de0`. Quest 1010 grants hammer 30297; its
enchantment 45131 targets worker template 40338. The driver uses the owned
hammer on individual workers and waits for native quest progress. It never
melees friendly workers. Inventory initialization now parses all occupied bag
slots, including a hammer that is not the first item in the first bag.

Live completion is verified for Arden: hammer spell 62068 was accepted, the
server reported quest 1010 READY and then FINISHED, and the bot turned it in
through the authored NPC. Awan has not completed this quest: he has encountered
movement failures on the approach and is now paused after repeated deaths in
fallback hunting. Do not describe his quest blockage as solved end to end.

## Following across public maps

The route graph is restricted to public town/field node types 1 and 2, with
available collision assets. The controller walks to an authored gateway,
submits normal `CheckNodeExit`, then confirms the pending `TriggerNodeEvent` if
the gateway did not already transfer it automatically. Failed/denied links get
a cooldown. It waits for native map load before continuing, clears previous
map actors/targets and discards movement segments from the old map. Migration
does not create duplicate social workers. It does not bypass entry conditions,
follow arbitrary teleports, or implement instance mechanics.

The selected-target assist and cross-map follow changes are deployed on Arden;
human-led live tests are pending. Awan's running process predates these latest
two changes; both share the earlier solo quest/grind and attack-response assist
controller. Restarting Awan will load the same installed code, but his current
repeated-death pause needs to be respected rather than silently reset.

Reconnect planning also had a stale completion-hint file: Arden had completed
1008–1010 normally, but the file still ended at 1007, causing a later retry of
already-finished quest 1008. The existing read-only saved-state snapshot helper
was run for each dedicated bot, refreshing those hints without modifying game
progress. A new completion-hint writer in the workspace `probe_login.py` caches
future server-confirmed FINISHED updates atomically. That writer is not yet
loaded by either running process; include it in the next bot deployment. The
native mission-snapshot trailing completion vectors still need full decoding;
do not interpret the first state section as a complete finished-quest history.

## Chat

Dialogue remains local and scripted. The new voices use short casual lines
such as `yo`, `otw`, `farm bentar`, `gas`, and `beres`, selected for the current
activity. Ambient checks happen every three to six minutes and often remain
silent. Replies require the bot's name, have a small delay, and share the
90-second minimum interval. Bot-to-bot messages are ignored to prevent loops.
No player text is copied into command output and no external chat API is used.

This is limited intent recognition, not unrestricted conversation.

## Equipment and validation

Last inspected login snapshots showed both bots wearing items 10001, 10067,
10068 and 10069. Neither snapshot contained replacement equipment. These are
snapshots, not proof that every later loot packet has been inspected. Inventory
snapshots refresh after fallback hunting and looting. Automatic comparison and
equipping of upgrades remains unimplemented.

The offline suite currently passes 191 tests, including assist target expiry,
leadership changes, range/map checks, NPC and player exclusion, malformed spell
messages, solo-training exclusion, hammer ownership/packet shape, and chat
delays/rate limits, correlated leader-selection replies, public-map route
filtering, pending gateway events and denied transitions. Live testing has shown Arden performing quests 1008/1009/1010,
using the gathering skill 62033 and hammer spell 62068, earning items, and reaching level 5. Awan has
landed normal attacks against a higher-level Port Skandia enemy rather than
only rabbits. Neither observation proves full quest-chain coverage.

Deployment helper: `bots/deploy_activity.py`. It validates staged Python under
the VM runtime, backs up replaced files under
`/var/backups/ak-bots/shared-activity-*`, and restarts only the two bot units.
Native logout can be rejected during combat; a bounded socket close may leave
the old session present briefly. Do not restart the game or edit account flags
to bypass this: allow cleanup before reconnecting.
