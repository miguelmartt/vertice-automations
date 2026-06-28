#!/usr/bin/env bash
# VertiGuard · restart MariaDB -> one-line JSON.
set -uo pipefail
systemctl restart mariadb 2>/dev/null
sleep 1
st=$(systemctl is-active mariadb 2>/dev/null)
printf '{"ts":"%s","action":"restart_mariadb","ok":%s,"state":"%s"}\n' "$(date -Iseconds)" "$([ "$st" = active ] && echo true || echo false)" "$st"
