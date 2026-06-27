#!/usr/bin/env bash
# VertiGuard · count pending system updates (dnf) -> one-line JSON
set -uo pipefail
ts=$(date -Iseconds)
upd=$(dnf -q check-update 2>/dev/null | grep -E '^[a-zA-Z0-9].*\s' | grep -vE '^(Obsoleting|Last metadata)' | wc -l)
printf '{"ts":"%s","updates":%s}\n' "$ts" "${upd:-0}"
