#!/usr/bin/env bash
# VertiGuard · pending system updates (dnf or apt): how many, how many are security fixes, which, and
# whether a reboot is needed to apply what is already installed (a new kernel, for example) -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

names() { grep -E '^[a-zA-Z0-9].*\s' | grep -vE '^(Obsoleting|Last metadata|Security:)' | awk '{print $1}' | sed 's/\.[^.]*$//'; }

if command -v dnf >/dev/null 2>&1; then
  manager=dnf
  list=$(dnf -q check-update 2>/dev/null | names)
  security=$(dnf -q check-update --security 2>/dev/null | names | grep -c .)
  # needs-restarting -r exits 1 when a reboot is needed; without the plugin, assume it is not.
  reboot=false
  if dnf -q needs-restarting --help >/dev/null 2>&1 && ! dnf -q needs-restarting -r >/dev/null 2>&1; then
    reboot=true
  fi
elif command -v apt-get >/dev/null 2>&1; then
  manager=apt
  upgradable=$(apt list --upgradable 2>/dev/null | tail -n +2)
  list=$(printf '%s\n' "$upgradable" | cut -d/ -f1)
  security=$(printf '%s\n' "$upgradable" | grep -c -- '-security')
  if [ -e /var/run/reboot-required ]; then reboot=true; else reboot=false; fi
else
  printf '{"ts":"%s","configured":false}\n' "$(now)"
  exit 0
fi
n=$(printf '%s\n' "$list" | grep -c .)
packages=""
while read -r name; do
  [ -n "$name" ] && packages="$packages$(json_str "$name"),"
done < <(printf '%s\n' "$list" | sort -u | head -20)
printf '{"ts":"%s","configured":true,"manager":"%s","updates":%s,"security":%s,"reboot_required":%s,"packages":[%s]}\n' \
  "$(now)" "$manager" "${n:-0}" "${security:-0}" "$reboot" "${packages%,}"
