#!/usr/bin/env bash
# VertiGuard · restart the n8n Docker container -> one-line JSON.
set -uo pipefail
C="${N8N_CONTAINER:-n8n}"
docker restart "$C" >/dev/null 2>&1
sleep 2
st=$(docker inspect -f '{{.State.Status}}' "$C" 2>/dev/null)
printf '{"ts":"%s","action":"restart_n8n","ok":%s,"state":"%s"}\n' "$(date -Iseconds)" "$([ "$st" = running ] && echo true || echo false)" "$st"
