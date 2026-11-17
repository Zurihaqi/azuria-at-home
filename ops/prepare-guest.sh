#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID == 0 ]] || exit 1
cd "$(dirname "$0")"
export DEBIAN_FRONTEND=noninteractive
# Only the archived security repository needs its historical validity date allowed.
sed -i 's|^deb http://archive.debian.org/debian-security|deb [check-valid-until=no] http://archive.debian.org/debian-security|; s|^deb-src http://archive.debian.org/debian-security|deb-src [check-valid-until=no] http://archive.debian.org/debian-security|' /etc/apt/sources.list
apt-get update
apt-get install -y ca-certificates curl gnupg sudo nftables unzip perl locales postgresql-13
install -m 600 ak-firewall.nft /etc/ak-firewall.nft
nft add table inet ak_guard
nft -c -f /etc/ak-firewall.nft
install -m 644 ak-firewall.service /etc/systemd/system/ak-firewall.service
systemctl daemon-reload
systemctl enable --now ak-firewall.service
curl -fsSL https://pkgs.tailscale.com/stable/debian/bullseye.noarmor.gpg -o /usr/share/keyrings/tailscale-archive-keyring.gpg
curl -fsSL https://pkgs.tailscale.com/stable/debian/bullseye.tailscale-keyring.list -o /etc/apt/sources.list.d/tailscale.list
apt-get update
apt-get install -y tailscale
systemctl enable --now tailscaled
# This command displays a sign-in URL; the owner must authenticate it.
tailscale up --hostname=ak-v15 --timeout=20s
