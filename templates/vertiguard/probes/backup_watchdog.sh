#!/usr/bin/env bash
# VertiGuard · is today's backup on the remote (rclone)? -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

if [ -z "$BACKUP_REMOTE" ]; then
  printf '{"ts":"%s","configured":false}\n' "$(now)"
  exit 0
fi
today=$(date +%F)
count=$(rclone lsf "$BACKUP_REMOTE/" --include "${BACKUP_PREFIX}${today}*" 2>/dev/null | wc -l)
newest=$(rclone lsf "$BACKUP_REMOTE/" --include "${BACKUP_PREFIX}*" 2>/dev/null | sort | tail -1)
printf '{"ts":"%s","configured":true,"today":"%s","today_count":%s,"newest":%s}\n' \
  "$(now)" "$today" "${count:-0}" "$(json_str "$newest")"
