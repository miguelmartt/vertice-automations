#!/usr/bin/env bash
# =============================================================================
# VertiGuard · installer
# Creates a dedicated low-privilege user for n8n, a restricted sudoers rule,
# a dedicated SSH key, and installs the monitoring scripts into /opt/vertiguard.
# Run as root on the VPS (tested on AlmaLinux 9 / RHEL-family). Mostly idempotent.
# =============================================================================
set -euo pipefail

# --- Config (override via environment) -------------------------------------
VG_USER="${VG_USER:-vertiguard}"           # dedicated user n8n logs in as
VG_DIR="${VG_DIR:-/opt/vertiguard}"        # where module scripts live
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "### 1) Dedicated user '$VG_USER' ###"
id "$VG_USER" &>/dev/null || useradd -m -s /bin/bash "$VG_USER"
echo "OK"

echo "### 2) Install module scripts into $VG_DIR ###"
mkdir -p "$VG_DIR"
cp "$SCRIPT_DIR"/*.sh "$VG_DIR"/
# never copy the installer itself as a runnable module
rm -f "$VG_DIR/install.sh"
chown root:root "$VG_DIR"/*.sh
chmod 755 "$VG_DIR"/*.sh
echo "OK ($(ls "$VG_DIR"/*.sh | wc -l) scripts)"

echo "### 3) Restricted sudoers: '$VG_USER' may run only $VG_DIR/*.sh, no password ###"
cat > /etc/sudoers.d/vertiguard <<SUDO
$VG_USER ALL=(root) NOPASSWD: $VG_DIR/*.sh
SUDO
chmod 440 /etc/sudoers.d/vertiguard
visudo -cf /etc/sudoers.d/vertiguard
echo "OK"

echo "### 4) Dedicated SSH key for n8n (ed25519, no passphrase) ###"
install -d -m 700 -o "$VG_USER" -g "$VG_USER" "/home/$VG_USER/.ssh"
KEY="/home/$VG_USER/.ssh/n8n_vertiguard"
if [ ! -f "$KEY" ]; then
  ssh-keygen -t ed25519 -f "$KEY" -N "" -C "n8n-vertiguard"
fi
touch "/home/$VG_USER/.ssh/authorized_keys"
grep -qF "$(cat "$KEY.pub")" "/home/$VG_USER/.ssh/authorized_keys" \
  || cat "$KEY.pub" >> "/home/$VG_USER/.ssh/authorized_keys"
chmod 600 "/home/$VG_USER/.ssh/authorized_keys"
chown -R "$VG_USER:$VG_USER" "/home/$VG_USER/.ssh"
echo "OK"

echo
echo "============================================================"
echo "Done. Next steps:"
echo "  1) Copy the PRIVATE key below into an n8n 'SSH' credential"
echo "     (host = this server, user = $VG_USER, auth = private key)."
echo "  2) Import the workflow JSONs and map the SSH + Telegram credentials."
echo
echo "=== PRIVATE KEY for the n8n SSH credential (paste it whole) ==="
cat "$KEY"
echo "============================================================"
