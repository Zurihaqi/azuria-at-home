# Connect and administer

- VM: AuraKingdom-V15; Debian 11.11; 4 vCPU, 4 GiB RAM, 80 GiB dynamic disk.
- Server VPN address: **100.64.0.10** (example Tailscale IP; see `private/network-config.json`). Windows owner: **100.64.0.1**.
- Open **Play Aura Kingdom.lnk** in the workspace, or client/Requiem Aurakingdom/Game.exe. Approve the client's elevation prompt if shown. The RequiemLauncher.exe updater belongs to the original service and can replace custom files.
- Log in inside the game. The generated accounts are gmadmin, playerone, and playertwo; passwords are in private/game-accounts.json. Character GM privileges require a character to exist first.
- connect.ini and connects.ini now use 100.64.0.10:6543. C_SysSetup.ini revision was aligned from 004 to the server's 001; original files are retained under private/client-original. This configuration change still requires gameplay compatibility testing.

## Administration from this workspace

`python ops/vm.py run 'systemctl status aurakingdom --no-pager'`

Replace the command with `systemctl start aurakingdom`, `systemctl stop aurakingdom`, or `journalctl -u aurakingdom -n 30 --no-pager` as needed. The helper authenticates using the encrypted key in private/. Windows loopback port 22222 forwards only to guest SSH.

## Inviting friends

Friends need Tailscale and explicit access to the VM in your tailnet. Their Tailscale IPv4 addresses must also be added to the players_v4 set in /etc/ak-firewall.nft, followed by systemctl reload ak-firewall. Do not add them to admins_v4. Configure their matching client with the same server address. Current allowed game TCP ports: 6543, 5567, 10020. SSH is owner-only; PostgreSQL and internal service ports are blocked from players.

## Backups

Daily timer: ak-backup.timer, 04:00 Asia/Jakarta. It briefly pauses game services for consistent database dumps, restarts them, then archives static server files. Successful backups have a COMPLETE marker and SHA256SUMS. The first backup was restored successfully into a separate socket-only PostgreSQL 13 cluster: see restore-report.json. Full game/VM restore and character persistence remain to be tested.
