#!/usr/bin/env bash
# VertiGuard · unban an IP from the fail2ban jail -> one-line JSON. Validates the IP first.
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

ip="${1:-}"
if ! [[ "$ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ || "$ip" =~ ^[0-9a-fA-F:]{2,39}$ ]]; then
  printf '{"ts":"%s","action":"unban","ok":false,"error":"invalid IP"}\n' "$(now)"
  exit 0
fi
if out=$(fail2ban-client set "$JAIL" unbanip "$ip" 2>&1); then ok=true; else ok=false; fi
printf '{"ts":"%s","action":"unban","ok":%s,"ip":"%s","detail":%s}\n' "$(now)" "$ok" "$ip" "$(json_str "$out")"
