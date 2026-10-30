#!/usr/bin/env bash
# VertiGuard · disk and RAM usage, and uptime -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

disk=$(df -P / | awk 'NR==2{gsub(/%/,"",$5); print $5}')
ram=$(free | awk '/^Mem:/{printf "%d", ($2-$7)/$2*100}')
up=$(uptime -p 2>/dev/null)
printf '{"ts":"%s","disk_pct":%s,"ram_pct":%s,"uptime":%s}\n' "$(now)" "${disk:-0}" "${ram:-0}" "$(json_str "$up")"
