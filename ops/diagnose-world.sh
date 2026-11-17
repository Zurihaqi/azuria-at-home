#!/usr/bin/env bash
set -Eeuo pipefail
cd /root/hxsy/WorldServer
export LC_ALL=C LANG=C
timeout 15s gdb -batch -ex run -ex 'x/15i $pc-25' -ex 'info registers rax rbx rcx rdx rsi rdi rbp' -ex 'info locals' -ex 'disassemble lapis::GetIfAddrs' --args ./WorldServer
