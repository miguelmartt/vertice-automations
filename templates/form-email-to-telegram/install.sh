#!/usr/bin/env bash
# Contact form (email) → Telegram · installer. Run it as root from a clone of the repo:
#   sudo bash templates/form-email-to-telegram/install.sh
# Re-running it updates the code and keeps your settings. It never starts the service the first
# time; if it is already running, it restarts it with the new code.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME=form-to-telegram
OPT=/opt/$NAME
ETC=/etc/$NAME

[ "$(id -u)" = 0 ] || { echo "Run it as root." >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null \
  || { echo "This template needs python3 3.9 or newer." >&2; exit 1; }

echo "== User $NAME"
id "$NAME" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$NAME"

echo "== Code in $OPT"
install -d -m 755 -o root -g root "$OPT" "$OPT/app"
for f in "$OPT"/app/*.py; do
  [ -e "$f" ] || continue
  [ -e "$HERE/app/$(basename "$f")" ] || { rm -f "$f"; echo "   removed old $(basename "$f")"; }
done
install -m 644 -o root -g root "$HERE"/app/*.py "$OPT/app/"

echo "== Settings in $ETC (an existing file is kept)"
install -d -m 750 -o root -g "$NAME" "$ETC"
[ -e "$ETC/$NAME.env" ] || install -m 640 -o root -g "$NAME" "$HERE/$NAME.env.example" "$ETC/$NAME.env"
# Also on a file that was already there: it holds the mailbox password, so only root and the service read it.
chown root:"$NAME" "$ETC/$NAME.env"
chmod 640 "$ETC/$NAME.env"

echo "== systemd unit"
install -m 644 -o root -g root "$HERE/systemd/$NAME.service" "/etc/systemd/system/$NAME.service"
systemctl daemon-reload

if systemctl is-active --quiet "$NAME" && ! grep -qE '^FORM_FROM=[^[:space:]]' "$ETC/$NAME.env"; then
  # Settings from before FORM_FROM existed: the new code would not start, so the old one keeps running.
  cat <<EOF

$NAME is running the old code and was NOT restarted: the new one needs FORM_FROM.
  1) Set FORM_FROM in $ETC/$NAME.env (the address your website sends the form emails from, or any)
     and check DKIM_DOMAIN (see the README).
  2) Then:  systemctl restart $NAME
EOF
elif systemctl is-active --quiet "$NAME"; then
  systemctl restart "$NAME"
  echo "$NAME was running: restarted with the new code."
else
  cat <<EOF

Installed. Next:
  1) Put the mailbox, the address your website sends from (FORM_FROM), the bot token and your
     chat ID in $ETC/$NAME.env.
  2) Start it:  systemctl enable --now $NAME
     Watch it:  journalctl -u $NAME -f
EOF
fi
