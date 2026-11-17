One experimental bot, **Awan**, now connects to the normal Aurora Ch01 world.
The owner explicitly requested the normal world and scripted speech on
2026-10-26. The isolated lab is stopped. Awan uses a dedicated ordinary account,
an unprivileged Linux user (`akbots`), and private random credentials. It shares
the existing game services with human players; running it needs no extra world
or server shutdown.

The owner-requested tutorial skip is administrative and is not counted as bot
gameplay evidence. Normal-world tests then verified quests 1004–1009 through
ordinary packets: NPC dialogue, three deliveries, rewards, three combat kills,
and four wood-pile Gather actions. The server accepted Gather skill 62033 and
marked quest 1009 ready/finished. Awan reached level 3 through normal rewards.
Quest 1010 uses a quest item on friendly workers; that action is not yet verified.

The bot sends local English–Indonesian templates with a 90-second cooldown.
Addressing Awan with a simple greeting queues a fixed response under the same
cooldown. The server echoed Awan's actual greeting. Incoming human chat is not
logged or sent to an external service. Replies are scripted, not general AI.

VM service: `ak-bot-awan.service` (manually started transient unit; boot autostart
is not enabled). Stop with `systemctl stop ak-bot-awan`. This disconnects only
the bot. The client runs with `--normal-world --quests --chat --continuous`.
Ordinary quest-driver failures pause activity while retaining the connection;
transport/network failures can still disconnect it. This is not a validated
unattended population or full quest solver.

Dashboard Bots now reads `/var/lib/ak-bots/pilot` for this configured normal-world
identity, including live quest/combat logs, failures and chat confirmations.
Authenticated live monitoring verified one normal-world bot online while the
normal game services remained active. Refresh the dashboard to load updated UI.

Root-owned authorization: `/etc/ak-bots/normal-world.json`.
Private credentials/state: `/var/lib/ak-bots/pilot` (never copy into public docs).
Code: `/opt/ak-bot-prototype`; no game binary patches were made for this bot.
The approved bot-only location repair and its backup are recorded in
`/var/lib/ak-bots/pilot/location-report.json`. A single zero-human-player restart
was performed after the owner logged out to clear the server's cached spawn.
No human character rows were changed.
