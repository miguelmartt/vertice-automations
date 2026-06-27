#!/usr/bin/env bash
# VertiGuard · Let's Encrypt cert expiry (days left per cert) -> one-line JSON
set -uo pipefail
LE_LIVE="${LE_LIVE:-/etc/letsencrypt/live}"
ts=$(date -Iseconds); now=$(date +%s); items=""
for d in "$LE_LIVE"/*/; do
  name=$(basename "$d"); [ "$name" = "README" ] && continue
  cert="${d}fullchain.pem"; [ -f "$cert" ] || continue
  end=$(openssl x509 -enddate -noout -in "$cert" 2>/dev/null | cut -d= -f2)
  end_s=$(date -d "$end" +%s 2>/dev/null || echo 0)
  days=$(( (end_s - now) / 86400 ))
  items="${items}{\"name\":\"$name\",\"days\":$days},"
done
items="${items%,}"
printf '{"ts":"%s","certs":[%s]}\n' "$ts" "$items"
