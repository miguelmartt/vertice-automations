# VertiGuard — VPS monitoring and a DevOps bot on Telegram

VertiGuard watches a self-hosted Linux server and tells you on Telegram **only when something
changes**. A DevOps bot lets you check the server and run a few safe actions from your phone, and
UptimeRobot alerts can go through it too.

It is one small Python service (standard library only, nothing to `pip install`) plus a handful of
root scripts it calls through a narrow `sudo` rule.

> 🇪🇸 [Versión en español](README.es.md)

---

## What it does

| Check | When | Alerts |
|---|---|---|
| Services (systemd units) and websites (HTTP 2xx/3xx) | every 5 min | when something goes down or comes back |
| Disk `/` and RAM above a threshold (80 % by default) | every hour | when it crosses the threshold, both ways |
| Let's Encrypt certificates expiring (15 days by default) | daily, 09:00 | when one gets close, and when it is renewed |
| Today's backup on an rclone remote | daily, 06:00 | when it is missing, and when it is back |
| fail2ban jail report | daily, 09:00 | always (a short summary) |
| Pending system updates (dnf or apt) | Mondays, 09:00 | always |
| A check that cannot run (a script fails, a timeout…) | — | when it starts failing and when it works again |

**DevOps bot** (optional): send `/menu` for buttons — server status, disk, RAM, uptime, SSL,
fail2ban, backups, restart the services you allow (with a *Confirm* step) and unban an IP. Any other
message goes to **Gemini**, which can read a live snapshot of the server but cannot change anything.
The bot only answers your chat.

**UptimeRobot webhook** (optional): an external monitor catches what the server itself can't (the
whole machine down). VertiGuard receives its webhook and forwards the alert to the same chat.

Every message is available in English and Spanish (`LANGUAGE=en|es`).

---

## How it works

```
/opt/vertiguard/app/vertiguard.py  (user: vertiguard, systemd: vertiguard.service)
 ├─ alerts       scheduler → sudo /opt/vertiguard/<probe>.sh → JSON → Telegram if it changed
 ├─ bot          Telegram long polling → /menu buttons or Gemini → probes
 └─ uptimerobot  http://127.0.0.1:<port>/<path> ← nginx ← UptimeRobot
```

- The **probes** (`/opt/vertiguard/*.sh`) read the server and print one line of JSON. They run as
  root through one sudoers rule: `vertiguard ALL=(root) NOPASSWD: /opt/vertiguard/*.sh`. The
  service user can run those scripts and nothing else.
- What the probes look at is set in `/etc/vertiguard/probes.conf`. It is sourced as root, so the
  probes refuse to run if it (or its folder) is not owned by root or is writable by others.
- Only two actions change anything: `restart_service.sh` (only units listed in `RESTARTABLE`) and
  `unban_ip.sh` (validates the IP). The bot always asks for confirmation before a restart.
- The bot uses **long polling**: no webhook and no open port for Telegram. The UptimeRobot webhook
  listens on `127.0.0.1` only.
- What was last reported is kept in `/var/lib/vertiguard/state.json`, so a restart doesn't repeat
  alerts. Logs go to the journal: `journalctl -u vertiguard`.

---

## Requirements

- Linux with systemd, `sudo`, `curl`, `openssl` and **Python 3.9+** (AlmaLinux/RHEL 9, Debian 11+,
  Ubuntu 22.04+ ship it).
- Optional: fail2ban, rclone (for the backup check), Let's Encrypt certificates, a Google AI Studio
  key (for the Gemini chat), an UptimeRobot account.
- One or two Telegram bots from [@BotFather](https://t.me/BotFather) and your chat ID (ask
  [@userinfobot](https://t.me/userinfobot)).

---

## Install

```bash
git clone https://github.com/miguelmartt/vertice-automations.git
cd vertice-automations
sudo bash templates/vertiguard/install.sh
```

The installer creates the `vertiguard` system user, copies the code to `/opt/vertiguard`, writes the
sudoers rule, installs the systemd unit and creates the two settings files (it never overwrites
them). It does not start anything yet.

1. **What to watch** — edit `/etc/vertiguard/probes.conf`:

   | Setting | Example | Meaning |
   |---|---|---|
   | `SERVICES` | `"nginx mariadb"` | systemd units that must be running |
   | `URLS` | `"https://example.com"` | websites that must answer 2xx/3xx |
   | `RESTARTABLE` | `"nginx"` | units the bot may restart (empty = no restart buttons) |
   | `LE_LIVE` | `"/etc/letsencrypt/live"` | certificates folder |
   | `BACKUP_REMOTE` / `BACKUP_PREFIX` | `"b2:my-backups"` / `"backup-"` | rclone remote:path and file prefix before the date; empty remote = no backup check |
   | `JAIL` | `"sshd"` | fail2ban jail |

2. **Secrets and options** — edit `/etc/vertiguard/vertiguard.env`:

   | Setting | Meaning |
   |---|---|
   | `TELEGRAM_CHAT_ID` | your chat ID; alerts go there and the bot only answers it |
   | `ALERTS_BOT_TOKEN` | bot that sends the alerts |
   | `DEVOPS_BOT_TOKEN` | bot for `/menu` and Gemini; empty = no DevOps bot (it can be the same bot) |
   | `GEMINI_API_KEY`, `GEMINI_MODEL` | empty key = the bot only offers `/menu` |
   | `WEBHOOK_PORT`, `WEBHOOK_PATH` | UptimeRobot webhook on `127.0.0.1`; empty port = off |
   | `LANGUAGE`, `TIMEZONE` | `en`/`es`; time zone for the daily reports |
   | `RESOURCE_ALERT_PCT`, `SSL_ALERT_DAYS`, `REPORT_HOUR`, `BACKUP_CHECK_HOUR` | thresholds and times |

3. **Try a probe** as the service user, then start it:

   ```bash
   sudo -u vertiguard sudo -n /opt/vertiguard/check_services.sh
   sudo systemctl enable --now vertiguard
   journalctl -u vertiguard -f
   ```

   The log shows which parts are running (`alerts, bot, uptimerobot`). Send `/menu` to the DevOps bot.

### UptimeRobot (optional)

1. Set `WEBHOOK_PORT` (e.g. `5678`) and a hard-to-guess `WEBHOOK_PATH` in `vertiguard.env`.
2. Put a reverse proxy in front, for example in nginx:

   ```nginx
   location /webhook/ { proxy_pass http://127.0.0.1:5678; }
   ```

3. In UptimeRobot, add an alert contact of type **Webhook**, POST, JSON body, URL
   `https://your-domain/<WEBHOOK_PATH>`, with the variables `*monitorFriendlyName*`, `*monitorURL*`,
   `*alertType*`, `*alertDetails*` and `*alertDateTime*`.

---

## Update and uninstall

```bash
cd vertice-automations && git pull && sudo bash templates/vertiguard/install.sh   # keeps your settings
```

To remove it: `systemctl disable --now vertiguard`, then delete `/etc/systemd/system/vertiguard.service`,
`/etc/sudoers.d/vertiguard`, `/opt/vertiguard`, `/etc/vertiguard`, `/var/lib/vertiguard` and the user.

## Coming from the n8n version

The n8n workflows are kept in the [`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final)
tag. The probes and the sudoers rule are the same idea, so moving over is: stop the n8n workflows,
run the installer, fill in the two settings files and start the service. The DevOps bot removes the
webhook n8n had set on it by itself. Afterwards, delete the SSH key n8n used to log in as
`vertiguard`; nothing needs it now.

## Tests

```bash
cd templates/vertiguard && python3 -m unittest discover -s tests -t .
```
