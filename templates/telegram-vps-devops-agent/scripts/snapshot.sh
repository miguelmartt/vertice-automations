#!/usr/bin/env bash
# VertiGuard · combined read-only snapshot for the AI DevOps agent.
# Gathers fast health checks into a SINGLE JSON line. Read-only, changes nothing.
# (System-update count is intentionally excluded: `dnf check-update` is slow.)
set -uo pipefail

# --- Config (override via environment) -------------------------------------
N8N_CONTAINER="${N8N_CONTAINER:-n8n}"
WEB_MAIN_URL="${WEB_MAIN_URL:-https://example.com}"
WEB_APP_URL="${WEB_APP_URL:-https://n8n.example.com/healthz}"
LE_LIVE="${LE_LIVE:-/etc/letsencrypt/live}"
BACKUP_REMOTE="${BACKUP_REMOTE:-b2:my-backups}"
BACKUP_PREFIX="${BACKUP_PREFIX:-backup-}"
JAIL="${JAIL:-sshd}"
# ---------------------------------------------------------------------------

ts="$(date -Iseconds)"
sysd(){ systemctl is-active --quiet "$1" && echo OK || echo FAIL; }
dock(){ [ "$(docker inspect -f '{{.State.Status}}' "$1" 2>/dev/null)" = running ] && echo OK || echo FAIL; }
url(){ c="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1" 2>/dev/null)"; { [ -n "$c" ] && [ "$c" -ge 200 ] && [ "$c" -lt 400 ]; } && echo OK || echo "FAIL($c)"; }

# services
nginx="$(sysd nginx)"; mariadb="$(sysd mariadb)"; n8n="$(dock "$N8N_CONTAINER")"
web_main="$(url "$WEB_MAIN_URL")"; web_app="$(url "$WEB_APP_URL")"

# resources
disk=$(df -P / | awk 'NR==2{gsub(/%/,"",$5);print $5}')
ram=$(free | awk '/^Mem:/{printf "%d",($2-$7)/$2*100}')
up=$(uptime -p 2>/dev/null | tr -d '"')

# ssl
now=$(date +%s); ssl_items=""
for d in "$LE_LIVE"/*/; do
  name=$(basename "$d"); [ "$name" = "README" ] && continue
  cert="${d}fullchain.pem"; [ -f "$cert" ] || continue
  end=$(openssl x509 -enddate -noout -in "$cert" 2>/dev/null | cut -d= -f2)
  end_s=$(date -d "$end" +%s 2>/dev/null || echo 0)
  days=$(( (end_s - now) / 86400 ))
  ssl_items="${ssl_items}{\"name\":\"$name\",\"days\":$days},"
done
ssl_items="${ssl_items%,}"

# fail2ban
s=$(fail2ban-client status "$JAIL" 2>/dev/null)
num(){ echo "$s" | grep "$1" | grep -oE '[0-9]+' | head -1; }
cur_failed=$(num "Currently failed"); tot_failed=$(num "Total failed")
cur_banned=$(num "Currently banned"); tot_banned=$(num "Total banned")
ips=$(echo "$s" | grep "Banned IP list" | sed 's/.*list:[[:space:]]*//')

# backups
today=$(date +%F)
bk_cnt=$(rclone lsf "${BACKUP_REMOTE}/" --include "${BACKUP_PREFIX}${today}*" 2>/dev/null | wc -l)
bk_newest=$(rclone lsf "${BACKUP_REMOTE}/" 2>/dev/null | sort | tail -1)

printf '{"ts":"%s","services":{"nginx":"%s","mariadb":"%s","n8n":"%s","web_main":"%s","web_app":"%s"},"disk_pct":%s,"ram_pct":%s,"uptime":"%s","ssl":[%s],"fail2ban":{"cur_banned":%s,"tot_banned":%s,"cur_failed":%s,"tot_failed":%s,"banned_ips":"%s"},"backups":{"today":"%s","today_count":%s,"newest":"%s"}}\n' \
  "$ts" "$nginx" "$mariadb" "$n8n" "$web_main" "$web_app" \
  "$disk" "$ram" "$up" "$ssl_items" \
  "${cur_banned:-0}" "${tot_banned:-0}" "${cur_failed:-0}" "${tot_failed:-0}" "$ips" \
  "$today" "${bk_cnt:-0}" "$bk_newest"
