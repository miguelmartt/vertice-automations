#!/usr/bin/env bash
# Installs or updates the agency toolkit. Run it as root from this folder: sudo bash install.sh
#
#   code     /opt/agency-toolkit/app (replaced on every run)
#   config   /etc/agency-toolkit/agency-toolkit.env (created once, never overwritten)
#   state    /var/lib/agency-toolkit (created by systemd)
#   service  /etc/systemd/system/agency-toolkit.service (installed, not started)
set -euo pipefail

NAME=agency-toolkit
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_DIR="/opt/$NAME"
CONFIG_DIR="/etc/$NAME"
CONFIG_FILE="$CONFIG_DIR/$NAME.env"
UNIT_FILE="/etc/systemd/system/$NAME.service"

if [[ $EUID -ne 0 ]]; then
    echo "Run it as root: sudo bash $0" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required" >&2
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    echo "Python 3.9 or newer is required (python3 is $(python3 -V 2>&1))" >&2
    exit 1
fi

# System user that runs the service.
if ! id -u "$NAME" >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$NAME"
    echo "Created the system user $NAME"
fi

# Code: replaced as a whole, so files removed from the template do not linger.
rm -rf "${CODE_DIR:?}/app"
install -d -m 755 "$CODE_DIR" "$CODE_DIR/app"
install -m 644 "$SRC"/app/*.py "$SRC"/app/*.html "$CODE_DIR/app/"
install -m 644 "$SRC/invoice.example.json" "$CODE_DIR/"
echo "Installed the code in $CODE_DIR"

# Config: only the first time. Readable by the service, not by other users.
install -d -m 750 -o root -g "$NAME" "$CONFIG_DIR"
if [[ -e "$CONFIG_FILE" ]]; then
    echo "Kept the existing $CONFIG_FILE"
else
    install -m 640 -o root -g "$NAME" "$SRC/$NAME.env.example" "$CONFIG_FILE"
    echo "Created $CONFIG_FILE: fill it in before starting the service"
fi

# systemd unit.
install -m 644 "$SRC/systemd/$NAME.service" "$UNIT_FILE"
systemctl daemon-reload
echo "Installed $UNIT_FILE"

cat <<EOF

Done. Next steps:
  1. Edit $CONFIG_FILE
  2. systemctl enable --now $NAME     (or: systemctl restart $NAME after an update)
  3. journalctl -u $NAME -f           (shows which features are on)
EOF
