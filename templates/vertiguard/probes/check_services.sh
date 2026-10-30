#!/usr/bin/env bash
# VertiGuard · are the services running and the websites answering? -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

checks=""
for unit in $SERVICES; do
  if systemctl is-active --quiet "$unit"; then st=OK; else st=FAIL; fi
  checks="$checks$(json_str "$unit"):\"$st\","
done
for url in $URLS; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null)
  code=${code:-000}
  if [ "$code" -ge 200 ] && [ "$code" -lt 400 ]; then st=OK; else st="FAIL($code)"; fi
  checks="$checks$(json_str "$url"):$(json_str "$st"),"
done
printf '{"ts":"%s","checks":{%s}}\n' "$(now)" "${checks%,}"
