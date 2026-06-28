#!/usr/bin/env bash
# VertiGuard · restart nginx -> one-line JSON. Run via the dedicated user (sudo wildcard).
set -uo pipefail
systemctl restart nginx 2>/dev/null
sleep 1
st=$(systemctl is-active nginx 2>/dev/null)
printf '{"ts":"%s","action":"restart_nginx","ok":%s,"state":"%s"}\n' "$(date -Iseconds)" "$([ "$st" = active ] && echo true || echo false)" "$st"
