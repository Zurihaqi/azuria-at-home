# Acceptance record

| Test | Status | Evidence |
| --- | --- | --- |
| V15 server installed and database imports valid | Passed | Required tables present; zero import SQL errors |
| Six game processes healthy and listening | Passed startup check | World/Zone null-ifaddr guard; C locale; vsyscall enabled |
| Owner VPN can reach client-facing ports | Passed | TCP 6543, 5567, 10020 reachable |
| Database/internal ports blocked from owner VPN | Passed | TCP 5432, 5560, 5568, 7654, 7777 blocked |
| Login and channel list | Passed by user | User screenshot shows Ch01(OK) |
| Client system revision alignment | Passed login/creation | Zrymund created after changing client revision 004 to 001 |
| Character creation | Passed | Zrymund, playerone, ID 50000001; server reports 1 online player |
| Visible world entry/tutorial | Awaiting user confirmation | |
| Two concurrent ordinary players | Untested | |
| Character persistence after restart | Untested | |
| Main story without GM bypasses | Untested | |
| Combat, drops, equipment, skills | Untested | |
| Eidolon acquisition/summoning | Untested | |
| Party dungeon entry/completion | Untested | |
| Trade, mail, storage, guilds | Untested | |
| Crafting, auction house, item mall | Untested | |
| GM command authorization | Untested | GM account exists; no GM character yet |
| Friend connects from another ISP | Untested | |
| Uninvited VPN device denied | Untested | Firewall player allowlist configured; needs second device test |
| Database backup restoration | Passed | All 3 databases, 3 accounts restored into isolated PostgreSQL 13 cluster |
| Full VM/gameplay restoration | Untested | No character existed in first backup |

Record quest/map/item IDs, steps, timestamps, and logs for failures. Do not mark untested content working.
