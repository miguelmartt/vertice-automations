#!/usr/bin/env bash
# VertiGuard · full on-demand status snapshot -> one-line JSON
set -uo pipefail
N8N_CONTAINER="${N8N_CONTAINER:-n8n}"
WEB_MAIN_URL="${WEB_MAIN_URL:-https://example.com}"
WEB_APP_URL="${WEB_APP_URL:-https://n8n.example.com/healthz}"
ts=$(date -Iseconds)
sysd(){ systemctl is-active --quiet "$1" && echo OK || echo FAIL; }
dock(){ [ "$(docker inspect -f '{{.State.Status}}' "$1" 2>/dev/null)" = running ] && echo OK || echo FAIL; }
url(){ c="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1" 2>/dev/null)"; { [ -n "$c" ] && [ "$c" -ge 200 ] && [ "$c" -lt 400 ]; } && echo OK || echo "FAIL($c)"; }
disk=$(df -P / | awk 'NR==2{gsub(/%/,"",$5);print $5}')
ram=$(free | awk '/^Mem:/{printf "%d",($2-$7)/$2*100}')
up=$(uptime -p 2>/dev/null | tr -d '"')
printf '{"ts":"%s","nginx":"%s","mariadb":"%s","n8n":"%s","web_main":"%s","web_app":"%s","disk_pct":%s,"ram_pct":%s,"uptime":"%s"}\n' \
  "$ts" "$(sysd nginx)" "$(sysd mariadb)" "$(dock "$N8N_CONTAINER")" "$(url "$WEB_MAIN_URL")" "$(url "$WEB_APP_URL")" "$disk" "$ram" "$up"
