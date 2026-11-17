#!/usr/bin/env bash
set -Eeuo pipefail
pid=$(pgrep -x WorldServer)
gdb -q -batch -p "$pid" -ex 'source /root/read-mall-cache.py' -ex detach
