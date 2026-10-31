#!/bin/bash
# VertiGuard · the backups on the remote (rclone): name, size and date of each -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

if [ -z "$BACKUP_REMOTE" ]; then
  printf '{"ts":"%s","configured":false}\n' "$(now)"
  exit 0
fi
# rclone's JSON goes into the output as it is, so it has to be a list.
if ! files=$(rclone lsjson "$BACKUP_REMOTE/" --files-only --include "${BACKUP_PREFIX}*" 2>/dev/null) \
  || [[ $files != \[*\] ]]; then
  printf '{"error":%s}\n' "$(json_str "rclone could not list $BACKUP_REMOTE")"
  exit 1
fi
printf '{"ts":"%s","configured":true,"today":"%s","prefix":%s,"files":%s}\n' \
  "$(now)" "$(date +%F)" "$(json_str "$BACKUP_PREFIX")" "$(printf '%s' "$files" | tr -d '\n')"
