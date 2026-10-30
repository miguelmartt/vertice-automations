#!/usr/bin/env bash
# VertiGuard · how many system updates are pending (dnf or apt) -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

if command -v dnf >/dev/null 2>&1; then
  manager=dnf
  n=$(dnf -q check-update 2>/dev/null | grep -E '^[a-zA-Z0-9].*\s' | grep -cvE '^(Obsoleting|Last metadata)')
elif command -v apt-get >/dev/null 2>&1; then
  manager=apt
  n=$(apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null | grep -c '^Inst ')
else
  printf '{"ts":"%s","configured":false}\n' "$(now)"
  exit 0
fi
printf '{"ts":"%s","configured":true,"manager":"%s","updates":%s}\n' "$(now)" "$manager" "${n:-0}"
