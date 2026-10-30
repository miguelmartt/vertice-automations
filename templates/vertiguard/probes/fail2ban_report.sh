#!/usr/bin/env bash
# VertiGuard · fail2ban jail summary, plus the bans of the last 24 h -> one-line JSON
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

# "2026-10-30 15:44:01,123 fail2ban.actions [123]: NOTICE  [sshd] Ban 192.0.2.1"
cutoff=$(date -d '24 hours ago' '+%F %T')
bans_24h=$(cat /var/log/fail2ban.log /var/log/fail2ban.log.1 2>/dev/null \
  | awk -v c="$cutoff" -v j="[$JAIL] Ban " '($1 " " substr($2, 1, 8)) >= c && index($0, j)' | wc -l)

printf '{"ts":"%s","configured":true,"jail":%s,"cur_failed":%s,"tot_failed":%s,"cur_banned":%s,"tot_banned":%s,"bans_24h":%s,"banned_ips":%s}\n' \
  "$(now)" "$(json_str "$JAIL")" "$(num 'Currently failed')" "$(num 'Total failed')" \
  "$(num 'Currently banned')" "$(num 'Total banned')" "${bans_24h:-0}" "$(json_str "$ips")"
