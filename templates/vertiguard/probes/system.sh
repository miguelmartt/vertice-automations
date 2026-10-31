#!/bin/bash
# VertiGuard · CPU, memory, disks, uptime and the processes using most memory -> one-line JSON
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# Every number below is checked with is_uint / is_num before $(( )) or the JSON (see lib/common.sh),
# and 10# keeps a leading zero from being read as octal.

# Current CPU use: two samples of /proc/stat half a second apart.
cpu_sample() { awk '/^cpu /{idle=$5+$6; total=0; for (i=2; i<=NF; i++) total+=$i; print total, idle}' /proc/stat; }
read -r t1 i1 < <(cpu_sample)
sleep 0.5
read -r t2 i2 < <(cpu_sample)
cpu=0
if is_uint "$t1" && is_uint "$i1" && is_uint "$t2" && is_uint "$i2" && (( 10#$t2 > 10#$t1 )); then
  cpu=$(( 100 * ((10#$t2 - 10#$t1) - (10#$i2 - 10#$i1)) / (10#$t2 - 10#$t1) ))
fi

read -r load1 load5 load15 _ < /proc/loadavg
is_num "$load1" || load1=0
is_num "$load5" || load5=0
is_num "$load15" || load15=0
cores=$(nproc 2>/dev/null)
is_uint "$cores" || cores=1
uptime_s=$(cut -d. -f1 /proc/uptime)
is_uint "$uptime_s" || uptime_s=0
mem=$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} /^SwapTotal:/{st=$2} /^SwapFree:/{sf=$2}
  END {printf "\"mem_total\":%d,\"mem_available\":%d,\"swap_total\":%d,\"swap_free\":%d", t*1024, a*1024, st*1024, sf*1024}' /proc/meminfo)

# No device column: a device or FUSE name picked by a user can't shift the fields, and the mount point
# (which may have spaces) is the last one. Lines whose numbers don't check out are skipped.
disks=""
while read -r size used pct mount; do
  case $mount in /boot | /boot/*) continue ;; esac
  is_uint "$size" && is_uint "$used" && [[ $pct =~ ^[0-9]+%$ ]] || continue
  pct=${pct%\%}
  disks="$disks{\"mount\":$(json_str "$mount"),\"size\":$((10#$size * 1024)),\"used\":$((10#$used * 1024)),\"pct\":$((10#$pct))},"
done < <(df -k --output=size,used,pcent,target -x tmpfs -x devtmpfs -x overlay -x squashfs -x efivarfs 2>/dev/null | tail -n +2)

procs=""
while read -r rss pcpu comm; do
  is_uint "$rss" && is_num "$pcpu" || continue
  procs="$procs{\"name\":$(json_str "$comm"),\"rss\":$((10#$rss * 1024)),\"cpu\":$pcpu},"
done < <(ps -eo rss=,pcpu=,comm= --sort=-rss | head -5)

os=$(sed -n 's/^PRETTY_NAME="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' /etc/os-release 2>/dev/null)
printf '{"ts":"%s","host":%s,"os":%s,"kernel":%s,"uptime_s":%s,"cpu_pct":%s,"cores":%s,"load":[%s,%s,%s],%s,"disks":[%s],"top":[%s]}\n' \
  "$(now)" "$(json_str "$(hostname -s)")" "$(json_str "$os")" "$(json_str "$(uname -r)")" "$uptime_s" \
  "$cpu" "$cores" "$load1" "$load5" "$load15" "$mem" "${disks%,}" "${procs%,}"
