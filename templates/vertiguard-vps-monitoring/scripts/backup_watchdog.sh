#!/usr/bin/env bash
# VertiGuard · verify today's backup exists on a remote (rclone) -> one-line JSON
set -uo pipefail
# --- Config (override via environment) -------------------------------------
BACKUP_REMOTE="${BACKUP_REMOTE:-b2:my-backups}"   # any rclone remote:path
BACKUP_PREFIX="${BACKUP_PREFIX:-backup-}"          # filename prefix before the date
# ---------------------------------------------------------------------------
ts=$(date -Iseconds); today=$(date +%F)
cnt=$(rclone lsf "${BACKUP_REMOTE}/" --include "${BACKUP_PREFIX}${today}*" 2>/dev/null | wc -l)
newest=$(rclone lsf "${BACKUP_REMOTE}/" 2>/dev/null | sort | tail -1)
printf '{"ts":"%s","today":"%s","today_count":%s,"newest":"%s"}\n' "$ts" "$today" "${cnt:-0}" "$newest"
