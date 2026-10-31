#!/bin/bash
# VertiGuard · days left on each Let's Encrypt certificate -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

now_s=$(date +%s)
items=""
for d in "$LE_LIVE"/*/; do
  [ -d "$d" ] || continue
  name=$(basename "$d")
  cert="${d}fullchain.pem"
  [ -f "$cert" ] || continue
  end=$(openssl x509 -enddate -noout -in "$cert" 2>/dev/null | cut -d= -f2)
  end_s=$(date -d "$end" +%s 2>/dev/null)
  is_uint "$end_s" || end_s=0
  items="$items{\"name\":$(json_str "$name"),\"days\":$(( (10#$end_s - now_s) / 86400 ))},"
done
printf '{"ts":"%s","certs":[%s]}\n' "$(now)" "${items%,}"
