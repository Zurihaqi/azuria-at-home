# Operations

These instructions describe the target installation; check STATUS.md for what is actually installed.

## Services

Inside the VM: `systemctl start aurakingdom`, `systemctl stop aurakingdom`, `systemctl status aurakingdom`, and `journalctl -u aurakingdom -f`.
Run `bash /root/hxsy/fullinstaller.sh --doctor` for diagnosis. Do not rerun the installer to change an address: its database creation step drops existing game databases.

## Accounts and GM

Run `/root/hxsy/account_creator.sh` interactively to avoid putting passwords in command history or installer logs. Create ordinary accounts separately from the GM account. Create the GM character in-game before granting its character privilege 5. Verify the actual schema and select that one character explicitly; never update all characters. Command syntax remains unverified until the matching build's command definitions are available and tested.

## Backups

Install ops/backup.sh as /usr/local/sbin/ak-backup, mode 700. Install the supplied service and timer under /etc/systemd/system, reload systemd, and enable ak-backup.timer only after a successful manual backup.
The backup pauses gameplay while dumping all three databases and global roles, restarts game services, then archives static server files under /var/backups/aurakingdom. Only directories containing COMPLETE are successful backups. The initial validated backup is also copied under private/backups in the Windows workspace. Credentials are included, so restrict access. Monitor disk usage; automatic deletion is intentionally not configured.

## Restore drill

The first database restore drill passed in a separate PostgreSQL 13 cluster using a private Unix socket and no TCP listener. See restore-report.json. For a complete game restoration drill, use a separate isolated VM with PostgreSQL 13. Verify SHA256SUMS, restore global roles (the existing postgres role needs special handling), create three empty databases, and use pg_restore --exit-on-error for each dump. Extract server.tgz only inside that restore VM. Keep its networking disconnected from players until addresses are adjusted. Compare character/inventory counts and verify in-game persistence. Do not restore over production as a test.

## Network

Use VirtualBox NAT. Tailscale runs inside the VM and on each player PC. Players receive only game-port access; SSH is owner-only and PostgreSQL remains local. Confirm client-facing ports using configs and actual listeners rather than exposing all server-to-server ports. Do not enable router forwarding. VPN authorization needs the owner's Tailscale sign-in and explicit device/user access policy.
