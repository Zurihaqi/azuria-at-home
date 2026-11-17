# Astral Control — Aura Kingdom dashboard

Open **Start Dashboard.cmd** in the workspace. It starts a hidden local Python process and opens **http://127.0.0.1:8765**. Reopening the shortcut reuses the process. Use this exact address for sign-in, rather than `localhost`.

Your separate dashboard login is stored in **private/dashboard/LOGIN.txt**. Username: `admin`. The authentication database stores a salted PBKDF2 password hash. The initial password is also kept in the Git-ignored login file for your reference. Game passwords are never listed by the dashboard.

## Controls

- **Overview:** live service processes, online character count, accounts, mall stock, quick actions and recent activity. Refresh queries current server data.
- **Players:** search characters or accounts; create ordinary game accounts; change a character's level (1–99), gold, bound gold, Envoy/skill points or character GM privilege (5). Gold inputs use game gold: `1000` means 1,000 gold, stored as 1,000,000 base units. The upper bound is 2,000 gold to leave room for quest rewards. Quests, inventory and mastery choices are untouched.
- **Bots:** monitoring plus start/stop controls at `#bots`. Shows actual process/lab status, heartbeat freshness, last known character level/map/quest, task, failures and up to 250 recent sanitized events. Refreshes every five seconds while visible; severity and text filters are local. **Start** launches a profile on the normal world with the exact flags recorded by the last reviewed deployment (`deploy_activity.py` writes that record; it refuses when the realm is stopped or normal-world access is disabled). **Stop** halts only the bot unit — the game service, human characters and databases are untouched, and native quest progress is preserved. Population resizing stays out of scope.
- **Item Mall:** search by translated name or item ID, browse all 44 installed catalog categories, edit prices/quantities/availability and add listings for existing server/client items. Hide a listing instead of deleting it. Changing a price does not replace item templates or enhancement hooks. New IDs do not automatically acquire fortification/stars unless covered by the existing native enhancement mask. New category labels and new item templates need a matching client update outside the dashboard.
- **Events:** scheduled category sales and a maintenance calendar. Sale prices must be below regular prices. Items already priced at 1 AP cannot be discounted. Conflicting sales for the same category are refused. Maintenance entries are calendar records; they do not shut down the game. Native XP multipliers, boss spawning and quest events are not implemented here.
- **Operations:** start/stop/restart, three-database backup, service journal, backup inventory and dashboard audit history. Start powers on the VM if necessary. Stop keeps the VM, PostgreSQL and VPN running. Allow about a minute after startup for the channel.

## Offline changes and backups

Everyone must be logged out before player, account or mall edits, or stop/restart. The guest checks `quit` before stopping services and checks again afterwards. It refuses the edit if a connection raced the first check. The game is then backed up, edited using bounded SQL and restarted if it was previously running. A failed edit still attempts to restart the service. Dashboard mutations and guest operations are serialized. Do not run separate direct editing scripts at the same time.

Before-edit snapshots are under `/var/backups/aurakingdom/dashboard-<UTC timestamp>/` in the VM. The existing daily backup timer is unchanged. “Back up now” uses `pg_dump -Fc` for FFAccount, FFDB1 and FFMember without disconnecting players; individual database snapshots are consistent, but separate databases are not one shared transaction.

Restore is manual because it overwrites game data. Log everyone out, stop `aurakingdom`, save a fresh backup and follow **docs/OPERATIONS.md** with the selected dump. Test restoration separately before replacing live databases. No live restoration was performed while building this dashboard.

## Event scheduling and recovery

Keep the Windows PC and dashboard Python process running for automatic sales; leaving the browser tab open is unnecessary. Scheduling checks run every 30 seconds. Sales wait for all characters to be offline, then take a backup and restart to load prices. End times also wait for an offline window, so a sale can extend past its planned end if players stay online. An elapsed sale that never started is cancelled. Check each event's status and error text.

An original-price snapshot is persisted locally **before** a sale is applied. Interrupted activation is marked `ending`; the next scheduler pass restores original prices. Active/ending category stock is protected against dashboard edits. Never delete `private/dashboard/dashboard.sqlite` while a sale is active or ending: it holds the recovery snapshot. Manual database price changes during a sale can be overwritten by restoration.

## Local security and files

The server listens only on `127.0.0.1:8765`. No public firewall ports or VPN routes are added. Requests require the expected Host; writes require the exact local Origin plus a session CSRF token. Cookies are HttpOnly/SameSite Strict, expire after eight hours, and are invalidated on restart. Login failures are rate limited. Static serving is restricted to three explicit files. SSH checks the existing pinned host key and uses the existing encrypted private key. There is no arbitrary shell/SQL endpoint.

- Source: `dashboard/server.py`, `dashboard/agent.py`, `dashboard/static/`.
- Data/auth/events/audit: `private/dashboard/` (Git ignored).
- Process output: `private/dashboard-output.log`, `private/dashboard-error.log`.
- Tests: `python -m unittest discover -s dashboard -p test_dashboard.py -v`.
- Stop dashboard: use Task Manager to stop the Python process with command line `dashboard/server.py`. This does not stop the game. Keep it running while sales need automatic restoration.
- Reset dashboard login: stop dashboard, preserve the SQLite database, move `admin.json` and `LOGIN.txt` to a private backup folder, then relaunch to generate a new login. Do not reset game databases.

This is a local owner console. Remote admin access would need a separate authenticated HTTPS/VPN deployment.
