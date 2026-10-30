#!/usr/bin/env bash
# VertiGuard · fail2ban jail summary -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

if ! command -v fail2ban-client >/dev/null 2>&1; then
  printf '{"ts":"%s","configured":false}\n' "$(now)"
  exit 0
fi
s=$(fail2ban-client status "$JAIL" 2>/dev/null)
num() {
  local n
  n=$(echo "$s" | grep "$1" | grep -oE '[0-9]+' | head -1)
  echo "${n:-0}"
}
ips=$(echo "$s" | grep "Banned IP list" | sed 's/.*list:[[:space:]]*//')
printf '{"ts":"%s","configured":true,"jail":%s,"cur_failed":%s,"tot_failed":%s,"cur_banned":%s,"tot_banned":%s,"banned_ips":%s}\n' \
  "$(now)" "$(json_str "$JAIL")" "$(num 'Currently failed')" "$(num 'Total failed')" \
  "$(num 'Currently banned')" "$(num 'Total banned')" "$(json_str "$ips")"
