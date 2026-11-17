#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
nft list table inet ak_guard >/dev/null || { echo 'Install the restrictive ak_guard firewall first.' >&2; exit 1; }
cd "$(dirname "$0")/../vendor/AKF"
[[ ! -e /root/hxsy ]] || { echo 'Existing installation found; refusing destructive reinstall.' >&2; exit 1; }
for db in FFAccount FFDB1 FFMember; do
    if command -v psql >/dev/null && runuser -u postgres -- psql -tAc 'SELECT datname FROM pg_database' 2>/dev/null | grep -Fxq "$db"; then
        echo "Existing database $db found; refusing reinstall." >&2
        exit 1
    fi
done
ip=$(tailscale ip -4)
[[ $ip =~ ^100\.([0-9]{1,3}\.){2}[0-9]{1,3}$ ]] || { echo 'Authenticate Tailscale first.' >&2; exit 1; }
archive=${1:?Supply the verified server ZIP path}
[[ -s $archive ]] || exit 1
bash ./fullinstaller.sh --lang=en --ip="$ip" --archive="$archive" --pg-version=13 --service --non-interactive
echo 'Installation finished. Inspect SQL import errors and service diagnostics before starting the server.'
