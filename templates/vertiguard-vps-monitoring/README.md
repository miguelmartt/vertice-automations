# VertiGuard — VPS monitoring suite for n8n

Eight small, focused **n8n** workflows that watch a self-hosted Linux VPS and alert you on **Telegram**.
Each one runs a tiny hardened shell script over SSH, emits one-line JSON, and only messages you when
something actually changes — so you get signal, not noise.

> 🇪🇸 [Versión en español](README.es.md)

Tested on **AlmaLinux 9 / RHEL-family** with **n8n running in Docker**. Adapts easily to Debian/Ubuntu
(swap `dnf` for `apt` in the updates script).

---

## The workflows

| # | File | Trigger | What it watches | Alerts when |
|---|---|---|---|---|
| 01 | [`01-service-monitor.json`](workflows/01-service-monitor.json) | every 5 min | nginx, MariaDB, n8n (Docker), 2 URLs | a service goes down / recovers |
| 02 | [`02-disk-ram.json`](workflows/02-disk-ram.json) | hourly | disk `/` and RAM usage | usage crosses 80% (configurable) |
| 03 | [`03-ssl-expiry.json`](workflows/03-ssl-expiry.json) | daily 09:00 | Let's Encrypt certs | a cert has < 15 days left |
| 04 | [`04-backup-watchdog.json`](workflows/04-backup-watchdog.json) | daily 06:00 | today's backup on an rclone remote | today's copy is missing |
| 05 | [`05-fail2ban-report.json`](workflows/05-fail2ban-report.json) | daily 09:00 | fail2ban `sshd` jail | daily summary (banned IPs, attempts) |
| 06 | [`06-external-uptime.json`](workflows/06-external-uptime.json) | webhook | external dead-man / uptime ping | the server stops responding from outside |
| 07 | [`07-system-updates.json`](workflows/07-system-updates.json) | Mondays 09:00 | pending `dnf` updates | weekly count of pending packages |
| 19 | [`19-status-on-demand.json`](workflows/19-status-on-demand.json) | Telegram `/status` | full snapshot on request | you send `/status` to the bot |

> **Heads up:** Telegram allows only **one active Trigger per bot**. Workflow 19 uses a Telegram
> Trigger, so if you also want other Telegram-trigger workflows, use a second bot for them.

---

## Architecture

```
n8n (Docker)  ──SSH──▶  dedicated 'vertiguard' user  ──sudo──▶  /opt/vertiguard/*.sh
     │                                                              │
     └────────────────── parse JSON, compare state ◀───────────────┘
                                   │
                                   ▼
                          Telegram bot  ──▶  you
```

n8n in Docker can't see the host's `systemctl`/`docker`, so checks run over SSH as a **dedicated,
low-privilege user** (`vertiguard`) that can run **only** `/opt/vertiguard/*.sh` via a restricted
sudoers rule. The shell scripts emit JSON; the workflow's Code node compares against the previous
state (stored in workflow static data) and messages you **only on change**.

> ⚠️ **State persistence:** n8n only persists `staticData` when the workflow is **active (published)**,
> not on manual test runs. Activate the workflow for the "only on change" logic to work.

---

## Setup

### 1. Install on the VPS (as root)

```bash
git clone https://github.com/<your-user>/vertice-automations.git
cd vertice-automations/templates/vertiguard-vps-monitoring/scripts
sudo ./install.sh
```

`install.sh` creates the `vertiguard` user, installs the scripts into `/opt/vertiguard/`, adds the
restricted sudoers rule, generates a dedicated SSH key, and prints the **private key** at the end —
copy it into the n8n SSH credential.

Configurable via environment, e.g.:

```bash
sudo VG_USER=monitor N8N_CONTAINER=my-n8n ./install.sh
```

### 2. Create credentials in n8n

| Credential | Type | Notes |
|---|---|---|
| **VPS SSH** | SSH | Host = your server, user = `vertiguard`, auth = *Private Key* (paste the key from step 1) |
| **Telegram account** | Telegram API | Bot token from [@BotFather](https://t.me/BotFather) |

### 3. Import & configure each workflow

1. **Workflows → Import from File** → pick a `*.json`.
2. Map the **VPS SSH** and **Telegram account** credentials.
3. Replace **`YOUR_CHAT_ID`** in the Telegram node with your chat ID
   (get it from [@userinfobot](https://t.me/userinfobot)).
4. For **19-status-on-demand**, also set `ALLOWED_CHAT_ID` in the *Filter /status* Code node so only
   you can query the server.
5. **Activate** the workflow.

---

## Configuration reference

### Placeholders to replace (in the workflow JSON)

| Placeholder | Where | Replace with |
|---|---|---|
| `YOUR_CHAT_ID` | Telegram nodes | Your Telegram chat ID |
| `ALLOWED_CHAT_ID = 0` | WF 19, *Filter /status* | Your numeric chat ID |
| `example.com` / `n8n.example.com` | Code-node labels | Cosmetic labels for your domains |
| `REPLACE_ME` | credential ids | Resolved automatically when you map credentials |

### Script variables (override via environment in the scripts)

| Variable | Default | Used by |
|---|---|---|
| `N8N_CONTAINER` | `n8n` | `check_services.sh`, `status.sh` |
| `WEB_MAIN_URL` | `https://example.com` | `check_services.sh`, `status.sh` |
| `WEB_APP_URL` | `https://n8n.example.com/healthz` | `check_services.sh`, `status.sh` |
| `LE_LIVE` | `/etc/letsencrypt/live` | `ssl_check.sh` |
| `BACKUP_REMOTE` | `b2:my-backups` | `backup_watchdog.sh` |
| `BACKUP_PREFIX` | `backup-` | `backup_watchdog.sh` |
| `JAIL` | `sshd` | `fail2ban_report.sh` |

The simplest way to set these permanently is to edit the values at the top of each script in
`/opt/vertiguard/` after install.

### Tunable thresholds (in the workflow Code nodes)

- **02 Disk/RAM:** `const TH = 80;` → alert threshold in %.
- **03 SSL:** `const TH = 15;` → warn when fewer than N days left.

### Workflow 06 — external uptime

This one is a **webhook**, designed for a dead-man-switch service like
[Healthchecks.io](https://healthchecks.io) (free tier sends webhooks). Point the service's
"down" webhook at the workflow's production URL (`/webhook/external-uptime`). The Code node already
parses common payload shapes (Healthchecks.io, UptimeRobot, generic JSON).

---

## Security & privacy

- The n8n user is **dedicated and low-privilege**: it can run **only** `/opt/vertiguard/*.sh` via a
  scoped sudoers rule — nothing else.
- Scripts are **read-only probes** (status, counts, expiry days). They change nothing on the system.
- This template is **sanitized**: no real hosts, IPs, tokens, chat IDs, or keys. Keys and `.env` are
  git-ignored. Publishing the monitoring logic does not weaken your server — your real defenses (SSH
  keys, fail2ban, firewall) are not in here.

## License

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
