#!/usr/bin/env bash
# VertiGuard · Docker containers and what they use -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  printf '{"ts":"%s","configured":false}\n' "$(now)"
  exit 0
fi
containers=$(docker ps -a --format '{{json .}}' 2>/dev/null | paste -sd, -)
stats=$(docker stats --no-stream --format '{{json .}}' 2>/dev/null | paste -sd, -)
printf '{"ts":"%s","configured":true,"containers":[%s],"stats":[%s]}\n' "$(now)" "$containers" "$stats"
