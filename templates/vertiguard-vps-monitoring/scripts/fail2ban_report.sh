#!/usr/bin/env bash
# VertiGuard · fail2ban jail summary -> one-line JSON
set -uo pipefail
JAIL="${JAIL:-sshd}"
ts=$(date -Iseconds); s=$(fail2ban-client status "$JAIL" 2>/dev/null)
num(){ echo "$s" | grep "$1" | grep -oE '[0-9]+' | head -1; }
cur_failed=$(num "Currently failed"); tot_failed=$(num "Total failed")
cur_banned=$(num "Currently banned"); tot_banned=$(num "Total banned")
ips=$(echo "$s" | grep "Banned IP list" | sed 's/.*list:[[:space:]]*//')
printf '{"ts":"%s","cur_failed":%s,"tot_failed":%s,"cur_banned":%s,"tot_banned":%s,"banned_ips":"%s"}\n' \
  "$ts" "${cur_failed:-0}" "${tot_failed:-0}" "${cur_banned:-0}" "${tot_banned:-0}" "$ips"
