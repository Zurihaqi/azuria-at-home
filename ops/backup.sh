#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
umask 077
cd /tmp
exec 9>/run/ak-backup.lock
flock -n 9 || exit 1
dest="/var/backups/aurakingdom/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$dest"
was_active=0
systemctl is-active --quiet aurakingdom && was_active=1
finish() { if (( was_active )); then systemctl start aurakingdom; fi; }
trap finish EXIT
systemctl stop aurakingdom
for db in FFAccount FFDB1 FFMember; do
    runuser -u postgres -- pg_dump -Fc "$db" >"$dest/$db.dump"
    pg_restore --list "$dest/$db.dump" >"$dest/$db.contents"
done
runuser -u postgres -- pg_dumpall --globals-only >"$dest/globals.sql"
if (( was_active )); then
    systemctl start aurakingdom
    was_active=0
    for attempt in $(seq 1 45); do
        ss -ltnH | grep -q ':10020 ' && break
        sleep 2
    done
    ss -ltnH | grep -q ':10020 ' || { echo 'Game service failed to restart' >&2; exit 1; }
fi
tar --exclude='root/hxsy/Logs' --exclude='*.log' --exclude='Test.log*' --exclude='core' --exclude='core.*' -I 'gzip -1' -cf "$dest/server.tgz" -C / root/hxsy etc/ak-server.conf etc/ak-firewall.nft etc/systemd/system/ak-firewall.service etc/systemd/system/aurakingdom.service etc/systemd/system/aurakingdom.service.d
(cd "$dest" && sha256sum *.dump globals.sql server.tgz >SHA256SUMS)
touch "$dest/COMPLETE"
printf 'Backup completed: %s\n' "$dest"
