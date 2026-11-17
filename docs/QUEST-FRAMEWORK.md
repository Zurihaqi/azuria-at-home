# Aura Kingdom headless quest framework

Implementation started 28 October 2026. As of 31 October both Awan and Arden
run the shared framework in the normal game world, with fallback grinding,
native stat-point spending and the initial battle/owned-gear driver enabled.
See `QUEST-1017-INVESTIGATION.md` for the latest live diagnosis and changes.

## Goal and boundaries

Interpret the installed mission database into ordinary player actions, verify
the results against native mission state, and recover from bounded failures.
Shared drivers should cover many quests without writing a separate script for
each quest. Special mechanics require explicit, evidence-backed semantic
overrides until their general database relationships are understood.

The framework never completes quests, grants rewards, changes levels, or moves
characters through database writes or GM commands. Native NPC offers, entry
checks, inventory ownership, cooldowns and reward validation remain authoritative.

This is a deterministic execution framework. It is not a learned quest policy.
Its stage/outcome journal supplies useful future recovery-policy training data.

## Components

- `bots/content.py`: parses mission conditions, accept actions, objectives,
  return NPCs, rewards and scene spawn/area data.
- `bots/quests.py`: evaluates known prerequisites and orders active quests and
  reachable offers. Unknown conditions defer to the NPC's actual offer.
- `bots/quest_engine.py`: compiles immutable plans, chooses eligible quests,
  executes stages, verifies native results, categorizes failures and journals
  retry cooldowns.
- `bots/objectives.py`: ordinary talk, combat/drop, gather, travel, equipment,
  delivery and item-interaction adapters. These remain at different levels of
  validation; having an adapter does not prove every matching quest works.
- `bots/npc.py`, `inventory.py`, `item_stream.py`: dialogue/session state and
  packet-driven inventory observation. Bag initialization includes all occupied
  slots rather than only the first item.
- The native class-5 resource catalog prevents collection objects from being
  misclassified as combat targets; see `QUEST-1020-RESOURCE-FIX.md`.
- Quest 2092's hidden crafting prerequisite is handled through ordinary native
  combination recipes and owned materials; see `QUEST-2092-CRAFTING.md`.
- `bots/probe_login.py`: owns the encrypted game sessions and injects movement,
  current level/map, dialogue, inventory and reporting into the engine.

## Execution contract

Each attempt follows these stages:

1. Choose an active/ready quest or an available local offer. Exclude quests on
   retry cooldown and plans with unresolved semantics. A ready quest can be
   turned in even if its objective driver is unsupported.
2. Walk to the authored accepting NPC and request the normal offer. Continue
   only after native ACTIVE or READY is observed.
3. Execute normalized objective steps. Record whether this quest's native
   state, objective progress or personal counters changed. Unrelated movement,
   chat and another quest's updates are not evidence of progress.
4. Require native READY. A driver returning normally without progress is
   explicitly journaled; it is not counted as successful completion.
5. Walk to the authored turn-in NPC and claim rewards normally. Require native
   FINISHED before recording completion.

Action budgets are bounded: NPC approaches have a 60-second budget, objective
drivers 90 seconds for noncombat work and 240 seconds for combat objectives,
native READY verification 10 seconds, and recovery refresh 15 seconds. Quest
encounters have a 180-second limit and the enclosing autonomous quest slice
has a ten-minute budget. Party/shutdown interruptions do not consume retries;
recent native deaths are classified as combat losses and do consume retries.

## Failure recovery

Failures are categorized as navigation, NPC offer/dialogue, inventory/item,
unsupported content, no progress, action deadline or other native action.
Recovery closes stale dialogue/shop interaction, refreshes native inventory and
player information, and queries mission state. It does not fabricate progress.

Retries use per-quest exponential cooldowns: 60, 120, 240 seconds, eventually
capped at 30 minutes. Cooldowns persist across reconnects in the bot-local
`quest-attempts.json`. The file keeps at most 500 events and is size bounded,
private and atomically replaced. It stores attempt metadata rather than
authoritative character progression.

One failing offer no longer immediately terminates all quest selection. Another
eligible quest may be attempted; an unsupported mandatory main-line step is
still a real content-coverage blocker, never a reason to administratively skip it.

## Semantic overrides and real examples

Quest 1010 declares `MonsterKilled 40338`, but its accept action grants hammer
30297. Item enchant 45131 targets the sleeping workers. Its override selects an
owned-item interaction rather than melee. Arden's native READY, FINISHED and
NPC turn-in were verified live before the new engine was introduced.

Quest 1014 declares `CheckBuff` and grants refreshing potion 30300. The old
adapter only waited and therefore made no progress. The framework correctly
reported `returned_without_progress` and a failed READY check. The new override
uses the owned potion through the native ItemUse packet and requires native
READY. The live test confirmed potion spell 62054, native READY, a navigation
failure on the return route, then successful recovery and native turn-in of
1014. The same framework subsequently completed 1015 and 1016 and accepted
1017, reaching level 8. This is measured pilot coverage, not a whole-map claim.

These are explicit adaptations, not evidence that arbitrary item effects can
already be inferred automatically. Further effect/script resolution should
replace overrides where the database semantics are sufficiently understood.

## Reconnect state

Existing saved completion hints are loaded only for the configured character.
Future native FINISHED messages are cached atomically for reconnect planning.
They cannot bypass native offer validation. A read-only saved-state snapshot
helper refreshed the initially stale hints; no progression was written to SQL.

The mission snapshot's trailing completion vectors still need full decoding.
The first state section alone is not a complete list of finished quests. This
limits fresh reconstruction without existing hints and requires explicit tests
before restoring or replacing caches.

## Coverage and validation

`docs/quest-framework-coverage.json` inventories the installed mission-table
corpus. It currently contains 2,870 quests; 2,263 compile against declared
adapters. That number is static coverage, not live correctness coverage.

Unresolved collection sources, crafting, card battles and relationship
objectives are explicit blockers. Movement reliability, equipment upgrades,
healing/combat skills, explicit reward-choice policy and cross-map independent
quest planning remain incomplete. The present autonomous content boundary is
Port Skandia; parsing later quests does not expand that boundary.

The offline suite passes 202 tests. Framework tests cover acceptance/readiness/
completion verification, no-op drivers, unrelated progress, cancellation,
persisted backoff, alternate offers, unsupported ready turn-ins and semantic
overrides. Real multi-quest/reconnect tests remain necessary.

## Operation

Run the offline suite with `python -m unittest discover -s bots/tests -q`.
Generate a coverage report with:

```
python bots/quest_engine.py staging/ultimate/hxsy/Data/db/S_Mission.ini --output docs/quest-framework-coverage.json
```

VM code lives under `/opt/ak-bot-prototype`. The existing guarded deployment
helper accepts `arden --quest-framework-only` to restart only Arden in the
quest-only pilot. It backs up replaced code under
`/var/backups/ak-bots/shared-activity-*` and does not restart the game server.
Normal bot sessions still support their earlier autonomous controller when
that flag is omitted. Logs are visible through the existing dashboard bot feed;
the more detailed attempt journal remains VM local.

## Dashboard positions

Bot cards now show map and X/Y. The API prefers reported native coordinates,
then recent confirmed movement/correction events. It never carries a log
coordinate across a death/respawn or map boundary. A fixed-ID read-only saved
database position is a labeled fallback for older running processes, including
the paused Awan. Old observations display their observation time; saved values
are explicitly labeled and may lag.

Both deployed bots publish the last native coordinate and its observation time.
Saved database positions remain a labeled fallback. The dashboard suite passed
20 tests when this feature was introduced, and the authenticated live feed
returned coordinates for both dedicated bot profiles.
