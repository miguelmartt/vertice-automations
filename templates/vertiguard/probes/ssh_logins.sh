#!/usr/bin/env bash
# VertiGuard · SSH logins and failed attempts in the last 24 h, from the journal -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# Newer OpenSSH logs each session as sshd-session; both matches on the same field are OR-ed.
log=$(journalctl _COMM=sshd _COMM=sshd-session --since "24 hours ago" --no-pager -o short-iso 2>/dev/null)
accepted=$(printf '%s\n' "$log" | grep -c ' Accepted ')
failed=$(printf '%s\n' "$log" | grep -cE ' (Failed password|Invalid user) ')

# "2026-10-30T15:44:01+0100 host sshd[123]: Accepted publickey for root from 192.0.2.1 port 5555 ssh2"
last=""
while read -r ts _ _ _ method _ user _ ip _; do
  last="$last{\"time\":$(json_str "$ts"),\"user\":$(json_str "$user"),\"ip\":$(json_str "$ip"),\"method\":$(json_str "$method")},"
done < <(printf '%s\n' "$log" | grep ' Accepted ' | tail -3)

printf '{"ts":"%s","accepted":%s,"failed":%s,"last":[%s]}\n' "$(now)" "${accepted:-0}" "${failed:-0}" "${last%,}"
