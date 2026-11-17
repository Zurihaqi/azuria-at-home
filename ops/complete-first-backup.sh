#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
cd /tmp
exec 9>/run/ak-backup.lock
flock -n 9 || exit 1
dest=/var/backups/aurakingdom/20261024T141637Z
[[ -d $dest && ! -e $dest/COMPLETE ]] || exit 1
for db in FFAccount FFDB1 FFMember; do pg_restore --list "$dest/$db.dump" >/dev/null; done
tar --exclude='root/hxsy/Logs' --exclude='*.log' --exclude='Test.log*' --exclude='core' --exclude='core.*' -I 'gzip -1' -cf "$dest/server.tgz" -C / root/hxsy etc/ak-server.conf etc/ak-firewall.nft etc/systemd/system/ak-firewall.service etc/systemd/system/aurakingdom.service etc/systemd/system/aurakingdom.service.d
(cd "$dest" && sha256sum *.dump globals.sql server.tgz >SHA256SUMS)
touch "$dest/COMPLETE"
echo "Backup completed: $dest"
