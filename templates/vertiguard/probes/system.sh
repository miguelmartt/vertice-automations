#!/usr/bin/env bash
# VertiGuard · CPU, memory, disks, uptime and the processes using most memory -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# Current CPU use: two samples of /proc/stat half a second apart.
cpu_sample() { awk '/^cpu /{idle=$5+$6; total=0; for (i=2; i<=NF; i++) total+=$i; print total, idle}' /proc/stat; }
read -r t1 i1 < <(cpu_sample)
sleep 0.5
read -r t2 i2 < <(cpu_sample)
cpu=$(( t2 > t1 ? 100 * ((t2 - t1) - (i2 - i1)) / (t2 - t1) : 0 ))

read -r load1 load5 load15 _ < /proc/loadavg
cores=$(nproc 2>/dev/null || echo 1)
mem=$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} /^SwapTotal:/{st=$2} /^SwapFree:/{sf=$2}
  END {printf "\"mem_total\":%d,\"mem_available\":%d,\"swap_total\":%d,\"swap_free\":%d", t*1024, a*1024, st*1024, sf*1024}' /proc/meminfo)

disks=""
while read -r _ size used _ pct mount; do
  disks="$disks{\"mount\":$(json_str "$mount"),\"size\":$((size * 1024)),\"used\":$((used * 1024)),\"pct\":${pct%\%}},"
done < <(df -P -k -x tmpfs -x devtmpfs -x overlay -x squashfs -x efivarfs 2>/dev/null | tail -n +2 | grep -v ' /boot')

procs=""
while read -r rss pcpu comm; do
  procs="$procs{\"name\":$(json_str "$comm"),\"rss\":$((rss * 1024)),\"cpu\":$pcpu},"
done < <(ps -eo rss=,pcpu=,comm= --sort=-rss | head -5)

os=$(sed -n 's/^PRETTY_NAME="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' /etc/os-release 2>/dev/null)
printf '{"ts":"%s","host":%s,"os":%s,"kernel":%s,"uptime_s":%s,"cpu_pct":%s,"cores":%s,"load":[%s,%s,%s],%s,"disks":[%s],"top":[%s]}\n' \
  "$(now)" "$(json_str "$(hostname -s)")" "$(json_str "$os")" "$(json_str "$(uname -r)")" "$(cut -d. -f1 /proc/uptime)" \
  "$cpu" "$cores" "$load1" "$load5" "$load15" "$mem" "${disks%,}" "${procs%,}"
