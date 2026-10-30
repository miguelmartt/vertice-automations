#!/usr/bin/env bash
# VertiGuard · are the services running and the websites answering, and how fast? -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

checks=""
times=""
for unit in $SERVICES; do
  if systemctl is-active --quiet "$unit"; then st=OK; else st=FAIL; fi
  checks="$checks$(json_str "$unit"):\"$st\","
done
for url in $URLS; do
  out=$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 10 "$url" 2>/dev/null)
  code=${out%% *}
  code=${code:-000}
  ms=$(awk -v t="${out#* }" 'BEGIN {printf "%d", t * 1000}')
  if [ "$code" -ge 200 ] && [ "$code" -lt 400 ]; then st=OK; else st="FAIL($code)"; fi
  checks="$checks$(json_str "$url"):$(json_str "$st"),"
  times="$times$(json_str "$url"):${ms:-0},"
done
printf '{"ts":"%s","checks":{%s},"ms":{%s}}\n' "$(now)" "${checks%,}" "${times%,}"
