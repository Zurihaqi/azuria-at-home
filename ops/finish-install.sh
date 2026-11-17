#!/usr/bin/env bash
set -Eeuo pipefail
cd /root/hxsy
export AK_SOURCE_ONLY=1
source ./fullinstaller.sh
unset AK_SOURCE_ONLY
detect_os
PG_VERSION=13
INSTALL_DIR=/root/hxsy
SERVER_IP=$(tailscale ip -4)
for s in "${AK_SERVERS[@]}"; do chmod 750 "$INSTALL_DIR/$s/$s"; done
ak_conf_save "$INSTALL_DIR" en "$SERVER_IP"
install_service
echo 'Service installed. Reboot for vsyscall before starting it.'
