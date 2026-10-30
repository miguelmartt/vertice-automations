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

echo "== sudo rule: $SVC_USER may run $OPT/*.sh as root, and nothing else"
# sudo ignores files with a dot in their name, so the temporary file is never active.
printf '%s ALL=(root) NOPASSWD: %s/*.sh\n' "$SVC_USER" "$OPT" > /etc/sudoers.d/vertiguard.tmp
chmod 440 /etc/sudoers.d/vertiguard.tmp
visudo -cqf /etc/sudoers.d/vertiguard.tmp
mv /etc/sudoers.d/vertiguard.tmp /etc/sudoers.d/vertiguard

echo "== Settings in $ETC (existing files are kept)"
install -d -m 750 -o root -g "$SVC_USER" "$ETC"
[ -e "$ETC/vertiguard.env" ] || install -m 640 -o root -g "$SVC_USER" "$HERE/vertiguard.env.example" "$ETC/vertiguard.env"
[ -e "$ETC/probes.conf" ] || install -m 644 -o root -g root "$HERE/probes.conf.example" "$ETC/probes.conf"

echo "== systemd unit"
install -m 644 -o root -g root "$HERE/systemd/vertiguard.service" /etc/systemd/system/vertiguard.service
systemctl daemon-reload

if systemctl is-active --quiet vertiguard; then
  systemctl restart vertiguard
  echo "VertiGuard was running: restarted with the new code."
else
  cat <<EOF

Installed. Next:
  1) Edit $ETC/probes.conf: services, websites, backups, restartable units.
  2) Put your tokens and chat ID in $ETC/vertiguard.env.
  3) Try a probe as the service user:  sudo -u $SVC_USER sudo -n $OPT/check_services.sh
  4) Start it:  systemctl enable --now vertiguard
     Watch it:  journalctl -u vertiguard -f
EOF
fi
