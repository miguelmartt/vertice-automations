#!/bin/bash
# VertiGuard · restart one of the services listed in RESTARTABLE -> one-line JSON.
# With --list, prints that list (the DevOps bot builds its buttons from it).
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# Split with read, not by an unquoted $RESTARTABLE, so a * in it is never expanded into file names.
read -r -d '' -a restartable <<<"$RESTARTABLE"

if [ "${1:-}" = "--list" ]; then
  list=""
  for unit in "${restartable[@]}"; do list="$list$(json_str "$unit"),"; done
  printf '{"ts":"%s","restartable":[%s]}\n' "$(now)" "${list%,}"
  exit 0
fi

unit="${1:-}"
allowed=false
for u in "${restartable[@]}"; do [ "$u" = "$unit" ] && allowed=true; done
if ! $allowed; then
  printf '{"ts":"%s","action":"restart","service":%s,"ok":false,"error":"not in RESTARTABLE"}\n' "$(now)" "$(json_str "$unit")"
  exit 0
fi
systemctl restart -- "$unit" 2>/dev/null
sleep 1
state=$(systemctl is-active -- "$unit" 2>/dev/null)
printf '{"ts":"%s","action":"restart","service":%s,"ok":%s,"state":%s}\n' \
  "$(now)" "$(json_str "$unit")" "$([ "$state" = active ] && echo true || echo false)" "$(json_str "$state")"
