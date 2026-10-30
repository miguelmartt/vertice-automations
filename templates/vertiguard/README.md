# VertiGuard — VPS monitoring and a Telegram bot

VertiGuard watches a self-hosted Linux server through **one Telegram bot**: it alerts you **only when
something changes**, sends a **daily report** with everything that matters, and answers **commands**
and a panel of buttons to check the server and run a few safe actions from your phone.

It is one small Python service (standard library only, nothing to `pip install`) plus a handful of
root scripts it calls through a narrow `sudo` rule.

> 🇪🇸 [Versión en español](README.es.md)

---

## What it does

**Alerts on changes**, both ways (when something breaks and when it is back), never repeated:

| Check | When |
|---|---|
| Services (systemd units) and websites (HTTP 2xx/3xx) | every 5 min |
| Disk(s) and RAM above a threshold (80 % by default) | every hour |
| Let's Encrypt certificates about to expire (15 days by default) | daily |
| Today's backup on an rclone remote | daily, 06:00 |
| A check that cannot run (a script fails, a timeout…) | when it starts failing and when it works again |

**Daily report** (09:00 by default), one message with:

- an overall light: 🟢 all good, 🟡 warnings or 🔴 problems, with the reasons;
- services and websites, with response times;
- CPU, RAM and disk with bars, load and uptime;
- security in the last 24 h: IPs banned by fail2ban, new bans, failed SSH attempts, SSH logins and the last one;
- today's backup with its size, and how many are stored;
- certificates (the one that expires first), Docker containers with their memory;
- pending updates, how many are security fixes, and whether a reboot is needed to apply what is installed.

It comes with 🔄 *Refresh* and 📋 *Menu* buttons.

**Commands**, registered in Telegram's «/» menu (Spanish names with `LANGUAGE=es`; the English ones always work):

| Command | Shows |
|---|---|
| `/report` | the full report, now |
| `/services` | each service and website, with response times |
| `/resources` | CPU, RAM, swap, every disk, load, uptime, OS and the processes using most memory |
| `/security` | fail2ban (now, 24 h, total), SSH logins and failed attempts, last logins, banned IPs |
| `/backups` | today's backup and the latest ones with size and date |
| `/ssl` | every certificate, days left and expiry date |
| `/docker` | containers, state, CPU and memory |
| `/updates` | pending packages, security fixes, reboot needed, how to install them |
| `/menu` | a panel of buttons that opens each section in the same message |
| `/restart` | restart one of the services you allow, after a confirmation |
| `/unban` | unban an IP from fail2ban |
| `/help` | all of the above |

Any other message goes to **Gemini** (optional), which can read a live snapshot of the server but cannot
change anything. The bot only answers your chat. **UptimeRobot** alerts can come through it too.

Every message is available in English and Spanish (`LANGUAGE=en|es`).

---

## How it works

```
/opt/vertiguard/app/vertiguard.py  (user: vertiguard, systemd: vertiguard.service)
 ├─ alerts       scheduler → sudo /opt/vertiguard/<probe>.sh → JSON → Telegram if it changed; daily report
 ├─ bot          Telegram long polling → commands, buttons (edit the same message), Gemini → probes
 └─ uptimerobot  http://127.0.0.1:<port>/<path> ← nginx ← UptimeRobot
```

- The **probes** (`/opt/vertiguard/*.sh`) read the server and print one line of JSON: services,
  system, certificates, fail2ban, SSH logins, backups, Docker and updates. They run as root through one
  sudoers rule: `vertiguard ALL=(root) NOPASSWD: /opt/vertiguard/*.sh`. The service user can run those
  scripts and nothing else. Several run in parallel, so a command answers in a second or two; the
  updates check is slow, so it is cached for 6 hours (*Refresh* forces it).
- What the probes look at is set in `/etc/vertiguard/probes.conf`. It is sourced as root, so the
  probes refuse to run if it (or its folder) is not owned by root or is writable by others.
- Only two actions change anything: `restart_service.sh` (only units listed in `RESTARTABLE`) and
  `unban_ip.sh` (validates the IP). The bot always asks before a restart.
- The bot uses **long polling**: no webhook and no open port for Telegram. The UptimeRobot webhook
  listens on `127.0.0.1` only.
- What was last reported is kept in `/var/lib/vertiguard/state.json`, so a restart doesn't repeat
  alerts. Logs go to the journal: `journalctl -u vertiguard`.

---

## Requirements

- Linux with systemd, `sudo`, `curl`, `openssl` and **Python 3.9+** (AlmaLinux/RHEL 9, Debian 11+,
  Ubuntu 22.04+ ship it).
- Optional, each one adds its part of the report: fail2ban, rclone (backups), Let's Encrypt, Docker,
  journald (SSH logins), dnf or apt (updates), a Google AI Studio key (Gemini), an UptimeRobot account.
- A Telegram bot from [@BotFather](https://t.me/BotFather) and your chat ID (ask
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
   | `TELEGRAM_CHAT_ID` | your chat ID; everything goes there and the bot only answers it |
   | `BOT_TOKEN` | the bot: alerts, report, commands and buttons |
   | `COMMANDS` | `off` = the bot only sends alerts and the report |
   | `SERVER_NAME` | name shown in the messages (default: the hostname) |
   | `GEMINI_API_KEY`, `GEMINI_MODEL` | empty key = commands and buttons only |
   | `WEBHOOK_PORT`, `WEBHOOK_PATH` | UptimeRobot webhook on `127.0.0.1`; empty port = off |
   | `LANGUAGE`, `TIMEZONE` | `en`/`es`; time zone for the report and the times shown |
   | `REPORT_HOUR` | hour of the daily report (0-23), or `off` |
   | `BACKUP_CHECK_HOUR`, `RESOURCE_ALERT_PCT`, `SSL_ALERT_DAYS` | backup check hour and thresholds |

3. **Try a probe** as the service user, then start it:

   ```bash
   sudo -u vertiguard sudo -n /opt/vertiguard/system.sh
   sudo systemctl enable --now vertiguard
   journalctl -u vertiguard -f
   ```

   The log shows which parts are running (`alerts, bot, uptimerobot`). Open the bot in Telegram, send
   `/menu`, and type `/` to see every command.

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

From the first Python release (two bots): `ALERTS_BOT_TOKEN` is still read as `BOT_TOKEN`, and
`DEVOPS_BOT_TOKEN` is no longer used: commands now live in the same bot as the alerts.

To remove it: `systemctl disable --now vertiguard`, then delete `/etc/systemd/system/vertiguard.service`,
`/etc/sudoers.d/vertiguard`, `/opt/vertiguard`, `/etc/vertiguard`, `/var/lib/vertiguard` and the user.

## Coming from the n8n version

The n8n workflows are kept in the [`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final)
tag. The probes and the sudoers rule are the same idea, so moving over is: stop the n8n workflows,
run the installer, fill in the two settings files and start the service. The bot removes the webhook
n8n had set on it by itself. Afterwards, delete the SSH key n8n used to log in as `vertiguard`;
nothing needs it now.

## Tests

```bash
cd templates/vertiguard && python3 -m unittest discover -s tests -t .
```
