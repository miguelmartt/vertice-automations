# shellcheck shell=bash
# shellcheck disable=SC2034  # the settings below are used by the probes that source this file
# VertiGuard · shared by every probe: loads the probes config and helps print JSON.
# Sourced by the probes, never run on its own. Installed in /opt/vertiguard/lib/, outside the sudo rule.

# The probes run as root: a fixed PATH and locale whatever the caller had (/sbin and /bin for systems
# without a merged /usr), and nothing they create readable by others.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C
umask 077

PROBES_CONF=/etc/vertiguard/probes.conf

# A JSON string: backslashes and quotes escaped, newlines as \n, tabs as spaces and every other
# control character dropped (LC_ALL=C: bytes 0-31 and 127, never part of a UTF-8 character).
json_str() {
  local s=${1//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\t'/ }
  s=${s//[[:cntrl:]]/}
  printf '"%s"' "$s"
}

# Numbers read from a command are checked with these before they go into $(( )) or into the JSON as
# they are: bash would run a command hidden in a value like a[$(…)] while doing the arithmetic.
is_uint() { [[ ${1-} =~ ^[0-9]+$ ]]; }
is_num() { [[ ${1-} =~ ^[0-9]+(\.[0-9]+)?$ ]]; }

# The probes run as root through sudo, so the file they source must only be writable by root.
# Otherwise the unprivileged user could put commands in it and have root run them.
if [ -e "$PROBES_CONF" ]; then
  read -r conf_uid conf_mode < <(stat -c '%u %a' "$PROBES_CONF")
  read -r dir_uid dir_mode < <(stat -c '%u %a' "$(dirname "$PROBES_CONF")")
  if [ "$conf_uid" != 0 ] || [ "$dir_uid" != 0 ] || (( (8#$conf_mode & 8#022) || (8#$dir_mode & 8#022) )); then
    printf '{"error":%s}\n' "$(json_str "$PROBES_CONF and its folder must belong to root and not be writable by others")"
    exit 1
  fi
  # shellcheck source=/dev/null
  . "$PROBES_CONF"
fi

SERVICES="${SERVICES:-nginx}"
URLS="${URLS:-}"
RESTARTABLE="${RESTARTABLE:-}"
LE_LIVE="${LE_LIVE:-/etc/letsencrypt/live}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
BACKUP_PREFIX="${BACKUP_PREFIX:-backup-}"
JAIL="${JAIL:-sshd}"

now() { date -Iseconds; }
