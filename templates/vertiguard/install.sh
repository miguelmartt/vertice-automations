#!/usr/bin/env bash
# VertiGuard · installer. Run it as root from a clone of the repo:
#   sudo bash templates/vertiguard/install.sh
# Re-running it updates the code and keeps your settings. It never starts the service the first
# time; if VertiGuard is already running, it restarts it with the new code.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC_USER=vertiguard
OPT=/opt/vertiguard
ETC=/etc/vertiguard

[ "$(id -u)" = 0 ] || { echo "Run it as root." >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null \
  || { echo "VertiGuard needs python3 3.9 or newer." >&2; exit 1; }

echo "== User $SVC_USER"
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$SVC_USER"

# Copies the files matching a pattern into a folder and removes the ones the repo no longer ships,
# so no old script stays runnable as root.
# shellcheck disable=SC2086  # $pattern is a glob on purpose
sync_files() {
  local src_dir=$1 pattern=$2 dest=$3 mode=$4 f
  for f in "$dest"/$pattern; do
    [ -e "$f" ] || continue
    [ -e "$src_dir/$(basename "$f")" ] || { rm -f "$f"; echo "   removed old $(basename "$f")"; }
  done
  install -m "$mode" -o root -g root "$src_dir"/$pattern "$dest/"
}

echo "== Code in $OPT"
install -d -m 755 -o root -g root "$OPT" "$OPT/lib" "$OPT/app"
sync_files "$HERE/probes" "*.sh" "$OPT" 755
sync_files "$HERE/probes/lib" "*.sh" "$OPT/lib" 644
sync_files "$HERE/app" "*.py" "$OPT/app" 644

echo "== sudo rule: $SVC_USER may run the probes in $OPT as root, and nothing else"
# Each probe by name, exactly as the bot calls it: the read-only ones only without arguments (""),
# the two actions with the argument they check themselves. A new probe has to be added here too.
# sudo gives them a clean environment and a fixed PATH, so nothing the service user sets reaches root.
# sudo ignores files with a dot in their name, so the temporary file is never active.
cat > /etc/sudoers.d/vertiguard.tmp <<EOF
# Written by templates/vertiguard/install.sh; re-running it rewrites this file.
Cmnd_Alias VERTIGUARD_PROBES = $OPT/backup_watchdog.sh "", $OPT/check_services.sh "", \\
  $OPT/docker_status.sh "", $OPT/fail2ban_report.sh "", $OPT/ssh_logins.sh "", $OPT/ssl_check.sh "", \\
  $OPT/system.sh "", $OPT/updates_check.sh "", $OPT/restart_service.sh *, $OPT/unban_ip.sh *
Defaults:$SVC_USER env_reset, !env_keep, secure_path="/usr/sbin:/usr/bin:/sbin:/bin"
$SVC_USER ALL=(root) NOPASSWD: VERTIGUARD_PROBES
EOF
chmod 440 /etc/sudoers.d/vertiguard.tmp
if ! visudo -cqf /etc/sudoers.d/vertiguard.tmp; then
  rm -f /etc/sudoers.d/vertiguard.tmp
  echo "visudo rejected the new sudo rule; the old one (if any) is still in place." >&2
  exit 1
fi
mv /etc/sudoers.d/vertiguard.tmp /etc/sudoers.d/vertiguard

echo "== Settings in $ETC (existing files are kept)"
install -d -m 750 -o root -g "$SVC_USER" "$ETC"
[ -e "$ETC/vertiguard.env" ] || install -m 640 -o root -g "$SVC_USER" "$HERE/vertiguard.env.example" "$ETC/vertiguard.env"
# Also on a file that was already there: it holds the tokens, so only root and the service read it.
chown root:"$SVC_USER" "$ETC/vertiguard.env"
chmod 640 "$ETC/vertiguard.env"
[ -e "$ETC/probes.conf" ] || install -m 644 -o root -g root "$HERE/probes.conf.example" "$ETC/probes.conf"

echo "== systemd unit"
install -m 644 -o root -g root "$HERE/systemd/vertiguard.service" /etc/systemd/system/vertiguard.service
systemctl daemon-reload

if grep -qE '^WEBHOOK_PORT=[^[:space:]]' "$ETC/vertiguard.env" \
  && ! grep -qE '^WEBHOOK_TOKEN=[^[:space:]]{16}' "$ETC/vertiguard.env"; then
  echo "!! WEBHOOK_PORT is set but WEBHOOK_TOKEN is not (16+ characters): the UptimeRobot webhook stays off." >&2
  echo "   Make one with: openssl rand -hex 32  (and add it to UptimeRobot, see the README)." >&2
fi
if systemctl is-active --quiet vertiguard; then
  systemctl restart vertiguard
  echo "VertiGuard was running: restarted with the new code."
else
  cat <<EOF

Installed. Next:
  1) Edit $ETC/probes.conf: services, websites, backups, restartable units.
  2) Put your bot token and chat ID in $ETC/vertiguard.env (and WEBHOOK_TOKEN for UptimeRobot).
  3) Try a probe as the service user:  sudo -u $SVC_USER sudo -n $OPT/check_services.sh
  4) Start it:  systemctl enable --now vertiguard
     Watch it:  journalctl -u vertiguard -f
EOF
fi
