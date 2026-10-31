#!/bin/bash
# VertiGuard · SSH logins and failed attempts in the last 24 h, from the journal -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# Only what the SSH service itself logged. journald sets _SYSTEMD_UNIT from the process's cgroup, so
# another program can't write lines that pass for sshd's (_COMM can: it is just the process name).
# The unit is sshd.service on RHEL/AlmaLinux and ssh.service on Debian/Ubuntu; both matches are OR-ed.
log=$(journalctl _SYSTEMD_UNIT=sshd.service _SYSTEMD_UNIT=ssh.service --since "24 hours ago" --no-pager -o short-iso 2>/dev/null)

# "2026-10-30T15:44:01+0100 host sshd[123]: Accepted publickey for root from 192.0.2.1 port 5555 ssh2"
# Matched from the start of the line, so a user name a client made up ("Invalid user x Accepted …")
# can't pass for a login.
accepted_re='^([0-9][0-9T:.+-]*) [^ ]+ [^ ]+: Accepted ([a-z0-9/-]+) for ([^ ]+) from ([0-9a-fA-F:.]+) port [0-9]+( |$)'
failed_re='^[^ ]+ [^ ]+ [^ ]+: (Failed password|Invalid user) '
accepted=$(printf '%s\n' "$log" | grep -cE "$accepted_re")
failed=$(printf '%s\n' "$log" | grep -cE "$failed_re")

last=""
while IFS= read -r line; do
  [[ $line =~ $accepted_re ]] || continue
  ts=${BASH_REMATCH[1]} method=${BASH_REMATCH[2]} user=${BASH_REMATCH[3]} ip=${BASH_REMATCH[4]}
  last="$last{\"time\":$(json_str "$ts"),\"user\":$(json_str "$user"),\"ip\":$(json_str "$ip"),\"method\":$(json_str "$method")},"
done < <(printf '%s\n' "$log" | grep -E "$accepted_re" | tail -3)

printf '{"ts":"%s","accepted":%s,"failed":%s,"last":[%s]}\n' "$(now)" "${accepted:-0}" "${failed:-0}" "${last%,}"
