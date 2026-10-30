#!/usr/bin/env bash
# Installs or updates the Telegram personal assistant. Run it as root from this folder:
#
#   sudo bash install.sh
#
# Creates the personal-assistant user, copies the code to /opt/personal-assistant, the config to
# /etc/personal-assistant (never overwriting an existing one) and the systemd unit. It does not start
# the service the first time: fill in the config first (see the README). Running it again updates the
# code, and restarts the service if it is running.
set -euo pipefail

NAME=personal-assistant
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/$NAME"
CONF_DIR="/etc/$NAME"
CONF="$CONF_DIR/$NAME.env"
UNIT="/etc/systemd/system/$NAME.service"

if [[ $EUID -ne 0 ]]; then
    echo "Run it as root: sudo bash $0" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is not installed" >&2
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    echo "Python 3.9 or newer is needed (found $(python3 --version 2>&1))" >&2
    exit 1
fi

# System user and group, without a shell or a home.
if ! id -u "$NAME" >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$NAME"
    echo "Created the system user $NAME"
fi

# Code: replaced as a whole, so files removed from the template do not linger.
install -d -m 755 -o root -g root "$APP_DIR"
rm -rf "${APP_DIR:?}/app"
install -d -m 755 -o root -g root "$APP_DIR/app"
install -m 644 -o root -g root "$SRC"/app/*.py "$APP_DIR/app/"
echo "Installed the code in $APP_DIR/app"

# Config: readable by the service, writable only by root. An existing one is never touched.
install -d -m 750 -o root -g "$NAME" "$CONF_DIR"
if [[ -e "$CONF" ]]; then
    echo "Kept the existing $CONF"
else
    install -m 640 -o root -g "$NAME" "$SRC/$NAME.env.example" "$CONF"
    echo "Created $CONF: fill it in before starting the service"
fi

# systemd unit.
install -m 644 -o root -g root "$SRC/systemd/$NAME.service" "$UNIT"
systemctl daemon-reload
echo "Installed $UNIT"

if systemctl is-active --quiet "$NAME"; then
    systemctl restart "$NAME"
    echo "It was running: restarted with the new code"
else
    echo "When the config is ready: systemctl enable --now $NAME"
    echo "Then watch it with: journalctl -u $NAME -f"
fi
