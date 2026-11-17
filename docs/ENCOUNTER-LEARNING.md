# Local encounter-learning prototype

Updated 28 October 2026. This is the first small gameplay-learning component;
it does not replace quest, movement, combat, party, or recovery controllers.

## What runs

`bots/encounter_learning.py` provides an ordinary-bot encounter recorder, a local
supervised model, a held-out evaluation gate, model publication, and a CLI.
It uses Python's standard library and SQLite. There is no model download,
language-model API, external chat processing, GPU requirement, or game-database
progression write.

The recorder is integrated with the shared combat loop, so it can observe either
Awan or Arden when that character actually fights. Arden's companion behavior
does not automatically generate combat data while simply waiting/following.

Runtime modes:

- No learning flags: ordinary prototype behavior.
- `--encounter-learning`: record fights and periodically train/evaluate in
  **shadow mode**. The existing target policy still controls gameplay.
- `--encounter-learning --learned-targets`: additionally permit an approved model
  to rank allowlisted fallback-hunting targets. Missing, unapproved, unsupported,
  or malformed models retain the existing fallback.

The currently deployed launches use collection/shadow mode. Learned target
selection is **not enabled**.

## What the model learns

The model is contextual nearest-neighbour learning with a Beta-smoothed
completion estimate and a weighted geometric mean of successful fight duration.
It estimates:

1. Probability of a native solo completion in the observed context.
2. Duration of a successful fight.
3. Successful completions per second as a first ranking signal.

It is not reinforcement learning and does not learn raw movement or packet
generation. It does not yet predict XP efficiency: XP is stored as `NULL` until
its native attribution is implemented. It does not infer a monster's worth from
invented XP values.

Context includes map, bot level, enemy template/level, and an equipment/strategy
fingerprint. The fingerprint uses decoded worn item-instance data; a changed or
unrecognised setup causes abstention rather than assuming old results apply.
Current HP, complete resource state, and a full combat build are not validated
features yet. This limits what the completion estimate can explain and is one
reason to keep the first model advisory.

The current curated candidate catalog covers eight ordinary Port Skandia enemy
templates. Deployment verifies their level/type entries against the live
`S_Biology.ini`. Candidate selection also requires an authored scene spawn and a
bounded level difference. It does not select arbitrary NPCs, bosses, resources,
or enemies from unrestricted maps.

Unseen enemies require actual observations before learned ranking can use them.
Repeated fights against a single rabbit cannot establish that a different
enemy is safe. This version does not add autonomous exploration, stronger-enemy
travel, new quest support, skill rotations, or gear upgrading by itself.

## Real labels and exclusions

Recording begins when the ordinary combat controller engages a known target.
Outcomes come from incoming native game events, not from whether a request was
sent or whether a local loop returned without an error.

Training labels:

- `kill`: the bot's own native kill notification for the tracked target.
- `death`: the bot's own native death during that encounter.

Recorded but excluded from training:

- Assistance or a different actor dealing damage to the target.
- An additional enemy attacking the bot.
- External spells affecting the bot or its target.
- Unparsed multi-target spell events or malformed relevant spell headers.
- A target leaving visibility, a timeout, cancellation, disconnect, or migration.
- Missing/unverified equipment or level context, unsupported templates, and
  encounters belonging to any character except the two dedicated bot IDs.

Timeouts and disconnects are not relabelled as deaths. A death is recorded before
the gameplay coroutine can be cancelled by recovery. Repeated finish calls do
not duplicate an encounter.

The first exclusion filter was too broad: any nearby spell event could exclude
an otherwise solo fight. It now checks the participants in the verified native
single-target spell header. Cast/visual acknowledgements are not evidence of
assistance. Unknown multi-target events remain conservatively excluded.

The two old excluded observations remain excluded. Their missing reason is
reported as `legacy-unattributed`; they were not rewritten into clean labels.
New exclusions have explicit, bounded reason codes.

## Collection and training lifecycle

Each bot keeps its own private dataset and model:

```text
Awan:
  /var/lib/ak-bots/pilot/encounters.sqlite3
  /var/lib/ak-bots/pilot/encounter-model.json
Arden:
  /var/lib/ak-bots/arden/encounters.sqlite3
  /var/lib/ak-bots/arden/encounter-model.json
```

SQLite retains at most 5,000 observations. Training considers the latest 2,000
eligible examples. Files remain private to the runtime identity. No account
passwords, opaque tickets, chat content, or human-character snapshots are put
into this dataset.

The optional trainer checks every 30 seconds and attempts a new shadow fit
after at least 40 usable labels and then every 20 additional usable labels.
Snapshot reads stay on the SQLite connection's owning thread; model fitting
runs in a worker thread. A trainer failure is reported and stops the optional
trainer, not the game session.

Every connection run gets a separate dataset session ID. The gate requires:

- At least 40 usable labels across three separate runs.
- At least 30 labels in training and 10 in the latest held-out run.
- At least 10 evaluable held-out predictions, 60% prediction coverage, and five
  evaluable successful fight durations.
- Completion Brier score and log-duration error no worse than simple training
  baselines.

The whole latest run is held out. It is not randomly mixed into training.
The published examples are exactly the evaluated training set; the model is
not silently refitted on its holdout afterwards.

An ordinary long first run can collect many fights but cannot satisfy the
three-run gate alone. Normal later bot runs add independent session groups.
There is no reason to restart the game server merely to create training groups.

Model publication uses bounded JSON, private permissions, a unique temporary
file, and atomic replacement. Runtime inference rejects unsupported or
unapproved artifacts and abstains when nearby context support is inadequate.
An evaluation pass means the small prediction gate passed, not that an entire
autonomous gameplay policy has been validated.

## Manual inspection and fitting

Run these inside the VM. Use `akbots` so generated files remain readable by the
bot, instead of creating a root-owned private model the bot cannot open.

```bash
runuser -u akbots -- python3 /opt/ak-bot-prototype/encounter_learning.py status \
  --db /var/lib/ak-bots/pilot/encounters.sqlite3

runuser -u akbots -- python3 /opt/ak-bot-prototype/encounter_learning.py train \
  --db /var/lib/ak-bots/pilot/encounters.sqlite3 \
  --out /var/lib/ak-bots/pilot/encounter-model.json
```

The same commands work for Arden with `/var/lib/ak-bots/arden`. The status command
reports outcomes, usable-label count, run count, and exclusion causes. An
insufficient-data fit writes an explicitly unapproved artifact with the reason.
No synthetic fixtures are loaded into live datasets or live models.

The existing dashboard Bots page shows recording status, clean-label count,
model readiness, and its reason after a page refresh. Bot logs remain newest
first and distinguish a recorded clean outcome from an excluded observation.

## Connection fix and live evidence

The WorldServer has a distinct `CNC_CW_ServerKeepAlive`; the previous
`ServerHello` loop did not maintain its idle timer. The matching installed
binary's keepalive decoder was verified as:

```text
8 native strings, int32, 2 native strings, int16
```

The headless client leaves unavailable desktop/hardware strings empty. The
native world keepalive is sent periodically while its earlier socket is drained
independently. Zone liveness requests retain their own responses. No game-server
timeout setting or production binary was changed.

After resumption, both bots stayed online for over nine minutes, beyond the
old roughly six-minute failure window. The first corrected collection run
produced 43 clean outcomes, including a death followed by ordinary recovery.
This is a live integration check, not a multi-hour unattended soak.

The VM also experienced a large clock correction during the earlier attempted
run. Training durations use a monotonic clock, and a disconnect is censored.
Wall-clock jumps can still affect the native server's own timers; this document
does not claim to have fixed VM timekeeping.

## Operation and rollback

Bot units are `ak-bot-awan` and `ak-bot-arden`. They are transient manually
launched units; this work does not enable bot boot autostart or a reconnect
supervisor. Stopping a unit preserves native character progress and the dataset.

The guarded `bots/deploy_learning.py` requires both bots and the legacy lab to
be stopped, verifies the live enemy catalog, compiles staged code under the
VM's Python runtime, and backs up replaced bot code under
`/var/backups/ak-bots/encounter-learning-*`.

Routine bot-code changes do not require restarting `aurakingdom`. To disable
learning, relaunch the bots without `--encounter-learning`; to disable only
learned choices, omit `--learned-targets`. Do not restore a native game database
to roll back this optional learner.

## Validation and remaining work

The offline suite covers native encounter completion, cancellation, death before
recovery, storage failures, human-character exclusion, attribution, sparse and
unfamiliar context, model corruption, a dangerous fast target, chronological
holdout, failed gates, and atomic publication. Synthetic fixtures exist only in
temporary test databases.

Still required before promoting the model into active choices:

1. Several independent real collection runs and more than one enemy context.
2. Meaningful negative outcomes and varied equipment/level contexts, without
   deliberately exposing human characters or granting bot progression.
3. Better HP/resource and incoming-damage features with native validation.
4. A bounded exploration/content policy that obtains data beyond the current
   rabbit fallback through ordinary gameplay.
5. A real held-out evaluation that passes; a passing synthetic test is not it.
6. A short monitored active-policy trial against a fixed rules baseline.
7. Longer soak, VM suspend/resume, maintenance and reconnect tests.

The separate conversation brain remains unaffected. This is encounter
selection learning, not a complete learned MMO brain.

## Live evaluation update, 28 October 2026

The first real held-out evaluation used 53 training and 14 held-out clean
encounters from three sessions. Its Brier score was 0.0020298 versus the
baseline's 0.0013223; its log-duration MAE was 0.608962 versus 0.496531.
Both metrics were worse, so the model was correctly rejected. It has not been
promoted to active enemy selection.

A later read counted 120 total encounters and 107 usable labels. Collection
continues, but mostly starter-enemy observations cannot support reliable
predictions for unfamiliar enemies. The separate level-based hunting rules
and shared activity controller are documented in `BOT-SHARED-ACTIVITY.md`.
