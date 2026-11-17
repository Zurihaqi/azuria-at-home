# Aura Kingdom headless-player prototype

**Current planning handover (27 October 2026):**
[Bot technical design and handover](../docs/BOT-TECHNICAL-DESIGN-AND-HANDOVER.md).
It separates verified behavior, unresolved runtime failures, in-progress changes,
and the proposed gameplay/conversation architecture. Historical lab instructions
below are not a current normal-world deployment recipe.

The first local encounter-learning component is implemented in collection/shadow
mode. See [encounter-learning operation and limits](../docs/ENCOUNTER-LEARNING.md).
It is not a complete learned gameplay brain or a validated active target policy.

Status: feasibility prototype, **not a deployed bot population**. At the owner's
explicit request, one ordinary character, Awan, now runs in the normal world.
See `docs/NORMAL-WORLD-BOT.md` for verified progress and limitations. Lab-only
tools retain their namespace checks; the normal client requires separate
root-owned authorization and its dedicated identity.

## Owner-requested tutorial skip (2026-10-26)

The owner explicitly authorized completing the pilot's tutorial through the
database. `skip_pilot_tutorial.py` was run only against the isolated offline
Sword-and-Shield pilot AwanBotLab (50000005, account 2421). Quests 2001, 1001,
2008 and 1003 are finished; quest 1004 is untouched. The pilot was moved to map
2, Port Skandia, at the wake-up destination authored by buff 45356 (area 24,
501.128/351.068). A full pre-edit FFDB1 dump is recorded in
`docs/bot-tutorial-skip.json`. Other characters and the production database
were not edited. Level 1, ordinary privileges, inventory and currency remain.

`probe_login.py --verify-arrival` confirmed native map 2 entry, full map loading,
normal ten-second logout, and persisted coordinates. The pilot is offline and
production services are restored. This is an administrative skip, not proof
of autonomous tutorial combat. The current `--quests` command still has a
map-610 guard; adapting the quest follower to Port Skandia remains separate work.

## Quest-control approach

Use a deterministic quest loop: accept -> select the current objective -> use
native objective navigation -> perform the objective -> select the return
objective -> claim rewards. No machine learning or learned barrier avoidance is
needed or planned. Before extending manual collision routing, investigate and
reuse the existing objective-click/navigation behavior wherever it is available.

Read-only inspection found CNE_CZ_ZoneServerMissionGoto (58): MissionID short,
Type short, NpcID unsigned short, From short. Its handler checks item 40035 and
contains a transport path, so it must not be assumed to be ordinary autowalk or
sent blindly. CNC_CZ_ClientGoto (495) contains ID, X, Y, PerformanceMode and a
synchronization counter. The normal objective-click behavior still needs to be
traced to establish which navigation work the graphical client performs and
which operations are available to an ordinary headless connection. Production
was left running during this read-only investigation.

## Deterministic quest follower

`probe_login.py --quests` (optional `--weapon N`, default 1) follows the authored
mission table without inventing progress:

- `content.py` parses `S_Mission.ini` into quests, conditions, accept actions,
  objective commands, rewards and display items; `quests.py` evaluates the
  authored conditions and picks the next reachable offer.
- `npc.py` handles the two native quest flows: a virtual mission board
  (`accept_npc == 0`, operation 9 then 1) and a real NPC dialog (`ReplyDialog`
  position, then the listed mission operation).
- `objectives.py` drives only the objective kinds it can perform (equip, talk,
  kill, collect drops, collect, travel, buff, level). Progress is never sent by
  the client: every driver waits for the server's own
  `ClientUpdateMissionState` (`3` active, `4` ready, `1` finished).
- `combat.py` handles target selection, melee acknowledgement and treasure
  pickup; `inventory.py` remembers where server-granted items landed so equipping
  uses the real item container instead of a guessed slot.
- Movement is chunked through the verified `MoveSelf` contract with one
  acknowledgement-gated segment at a time.

The follower stops rather than guessing when a quest has an objective kind it
cannot drive, when a required NPC is not authored on the current map, or when
the server reports an unexpected state.

## Evidence so far

- Native encrypted login, world selection and zone entry work.
- An ordinary account creates a level-1 Sword-and-Shield character through the
  normal character-creation flow. No character progression is inserted by SQL.
- The pilot receives authoritative character, inventory, quest and nearby-actor
  state, completes map loading, walks to a tutorial NPC and receives dialogue.
- The native half-unit collision map is decoded. A* routes and obstacle avoidance
  pass synthetic tests; a real obstacle route still needs an in-game check.
- Quest 2001 is accepted normally and the server grants starter weapon 30275.
  Automatic equipment-slot selection succeeds (native weapon slot 5, page 0).
  Walking to the blacksmith, selecting the quest dialogue and claiming the reward
  completes the quest normally: native state 3 -> 4 -> 1.
- The first completion persists across logout: after reconnect, the blacksmith
  offers quest 1001, not 2001. The authored controller accepted 1001, walked to
  the commander, completed it and accepted combat quest 2008 normally. It resumes
  accepted quests from native state and handles the rapid 3-to-4 transition.
- Normal logout uses the server's ten-second countdown; reconnect has been tested.
- A human observer's normal client confirmed: open starter quest with operation
  9, accept with 1, select an NPC dialogue option with ReplyDialog, claim a
  completed quest with operation 2. These operations remain subject to native
  quest checks.
- Thirty-one protocol/navigation/movement tests pass, including MSB-first bag
  occupancy, the distinct bag-index/slot fields in equipment transfer packets,
  the eight-direction blob encoding and a full server-validated replay of the
  S610 route. The quest layer now adds parser, selection, dialogue and
  objective-driver tests; the whole suite is 124 tests and needs no network or
  database.

## Current blocker

Equipment rejection is resolved: close the normal quest/shop interaction first,
select the occupied bag slot using MSB-first occupancy, then request destination
slot -1 for native slot selection. The response name alone does not indicate
success: its OK byte must equal 1. The tutorial character panel is locked; no
further human unequip/reequip comparison is required.

The earlier apparent quest reset was a parser limitation: completed quests are
stored separately in MLComplete, outside the decoded active-state prefix. The
NPC's next-quest offer confirms first-quest persistence. A full completed-state
decoder remains pending. Temporary weapon removal during logout is observed;
normal tutorial weapon/buff restoration still needs verification before combat.

The first longer real-map obstacle route received a native coordinate correction
and did not reach its requested endpoint (209.75,104.75 instead of 215,115).
That is now root-caused rather than a server-side collision gate. The old pilot
sent an empty direction blob, put the previous point in the authoritative
`f1,f2` fields and reused a stale synchronization value, so the server never
advanced the character and kept re-issuing `ClientResetCoord`. `movement.py`
encodes the real contract: direction blob of `(steps << 3) | dir`, `f1,f2` set to
the blob endpoint, monotonic `sync` that never falls below the server's
`ch+0x35c` floor, and a local replica of `CNode::IsBlockGrid` so a route is
pre-validated before it is sent. The route to (210,178) now plans as 198 cells,
17 ack-gated segments and 25 blob bytes with zero hard-blocked cells. Live
acceptance is still unconfirmed; it is the first lab lease.

`walk()` now sends one validated segment at a time, waits for the server's own
self-move report, retries once with a fresh sync when a hop goes unconfirmed,
and replans from the corrected position without echoing a movement packet back.
A single starter Sword Slash probe exists but has not reached its target; no
combat success is claimed. Death packets for the pilot also pause the probe.

## Not implemented or validated yet

Combat, loot and the authored quest follower are implemented and unit-tested, but
their live acceptance runs are still outstanding. Human-visible co-presence,
party operations, the remaining starter quests, the full ten-quest chain,
dungeon behavior, personalities, persistent scheduling, dashboard bot controls,
maintenance draining, population classification and the 1-to-4-to-12
rollout/one-hour soak remain outstanding. The one-player feasibility gate has not
passed. Production bot autostart must remain disabled.

## Lab operation

The owner's existing dashboard has a read-only Bots page at
`http://127.0.0.1:8765/#bots`. `GET /api/bots` uses existing session authentication
and the SSH allowlist. No new administration listener or bot-start endpoint is
created. `reporting.py` writes bounded sanitized events and a heartbeat under
the lab's `/run/pilot`; the dashboard requires both a real pilot process and a
fresh heartbeat before showing it online. Stopped and stale states remain
distinct from prior outcomes. Arbitrary native log text and credentials are
never returned. The existing sanitized protocol trace supplies historical
request metadata for sessions predating structured reporting.

The Debian VM has 4 GB RAM. Do not run a second ZoneServer alongside production.
`lab.py` uses separate mount, network and PID namespaces, a copied game tree and
a restored PostgreSQL cluster. The full lab temporarily replaces the running
production game services; its systemd cleanup restores production. Production
database files are not mounted as the lab database.

`python ops/vm.py run` executes VM commands. Controller location:
`/root/ak-bot-explore/lab.py`. Renew the active fifteen-minute lab lease with:

```text
python3 /root/ak-bot-explore/lab.py enter true
```

Run the pilot as unprivileged `nobody` inside the namespace, never root. Identity
files and opaque tickets are private under the lab's `/run/pilot`. Do not print
them or expose them through dashboard responses. The controller verifies its
namespace marker before running a player probe.

The temporary observer relay exposes only the existing game endpoints on the
VM's VPN address. It forwards to the lab through root-only Unix sockets and
does not log packet payloads. The GDB trace attaches only to the lab ZoneServer,
captures allowlisted quest/equipment control fields, and excludes credentials,
authentication tickets, movement spam and chat payloads. Native game logs can
contain database credentials: use `lab_report.py` rather than printing raw logs.

Stop the lab with `lab.py stop` after coordinating with the human observer;
that closes their isolated-world session and restores production.
