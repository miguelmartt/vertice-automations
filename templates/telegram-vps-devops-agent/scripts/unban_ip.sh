#!/usr/bin/env bash
# VertiGuard · unban an IP from a fail2ban jail -> one-line JSON. Validates the IP.
set -uo pipefail
JAIL="${JAIL:-sshd}"
ip="${1:-}"
if ! echo "$ip" | grep -qE '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
  printf '{"ts":"%s","action":"unban_ip","ok":false,"error":"invalid IP"}\n' "$(date -Iseconds)"; exit 0
fi
out=$(fail2ban-client set "$JAIL" unbanip "$ip" 2>&1)
printf '{"ts":"%s","action":"unban_ip","ok":true,"ip":"%s","detail":"%s"}\n' "$(date -Iseconds)" "$ip" "$out"
