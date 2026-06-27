#!/usr/bin/env bash
# VertiGuard · disk & RAM usage -> one-line JSON
set -uo pipefail
disk=$(df -P / | awk 'NR==2{gsub(/%/,"",$5); print $5}')
ram=$(free | awk '/^Mem:/{printf "%d", ($2-$7)/$2*100}')
ts=$(date -Iseconds)
printf '{"ts":"%s","disk_pct":%s,"ram_pct":%s}\n' "$ts" "$disk" "$ram"
