# Telegram VPS DevOps agent (n8n + Gemini)

Run and inspect your **self-hosted VPS** from Telegram. Two ways to use it:

- **Free text** — ask in natural language (*"how's the server?"*, *"any attacks today?"*) and an AI
  agent (Gemini) fetches a live snapshot over SSH and answers.
- **`/menu`** — a button menu to tap: read status (services, disk, RAM, uptime, SSL, fail2ban,
  backups) and run **control actions** (restart nginx / n8n / MariaDB, unban an IP) — every control
  action behind an explicit **Confirm / Cancel** step.

> 🇪🇸 [Versión en español](README.es.md)

Built on the [`vertiguard-vps-monitoring`](../vertiguard-vps-monitoring/) scripts and the same
dedicated low-privilege SSH user. Tested on AlmaLinux 9 with n8n in Docker and a free Google Gemini key.

---

## How it works

```
Telegram (message or button tap)
   │
   ▼
Telegram Trigger ─▶ Guard (allowlist: only your chat) ─▶ Route
                                                          ├─ /menu  → send button menu (HTTP)
                                                          ├─ button → run snapshot / control + reply
                                                          └─ text   → AI Agent (Gemini + memory + tool)
```

- **Reads** run `snapshot.sh` over SSH and format the slice you asked for.
- **Control actions** show a confirmation; on *Confirm* they run a small, dedicated script
  (`restart_*.sh`, `unban_ip.sh`) over SSH and report the result.
- **Free text** goes to a Gemini agent with conversation memory and a `get_vps_status` tool.

Inline keyboards are sent via an **HTTP Request** node to the Telegram API (more reliable than the
native node's keyboard UI across versions).

Two workflows are included:

| File | Role |
|---|---|
| [`workflows/telegram-vps-devops-agent.json`](workflows/telegram-vps-devops-agent.json) | Main: trigger, router, menu, control + confirmation, AI text path |
| [`workflows/vps-snapshot-subworkflow.json`](workflows/vps-snapshot-subworkflow.json) | Tool target for the AI agent: runs `snapshot.sh` and returns the JSON |

---

## Scripts (install on the VPS, in `/opt/vertiguard/`)

| Script | Purpose |
|---|---|
| `snapshot.sh` | Combined read-only snapshot (services, disk, RAM, uptime, SSL, fail2ban, backups) |
| `restart_nginx.sh` | `systemctl restart nginx` + report |
| `restart_n8n.sh` | `docker restart` the n8n container + report |
| `restart_mariadb.sh` | `systemctl restart mariadb` + report |
| `unban_ip.sh <ip>` | `fail2ban-client unban` (validates the IP) |

All emit one-line JSON and run as the dedicated `vertiguard` user via the scoped sudoers rule
(`/opt/vertiguard/*.sh`) — no extra privilege beyond that wildcard.

---

## Setup

### 1. Install the scripts on the VPS (as root)

You need the VertiGuard base (dedicated `vertiguard` user + scoped sudoers) — if you use
[`vertiguard-vps-monitoring`](../vertiguard-vps-monitoring/), you already have it.

```bash
sudo install -m 755 -o root -g root snapshot.sh restart_nginx.sh restart_n8n.sh \
  restart_mariadb.sh unban_ip.sh /opt/vertiguard/
sudo -u vertiguard sudo -n /opt/vertiguard/snapshot.sh   # test: prints one JSON line
```

Edit the config vars at the top of `snapshot.sh` (domains, container, backup remote) and set
`N8N_CONTAINER` in `restart_n8n.sh` if your container isn't named `n8n`.

### 2. Create a dedicated Telegram bot

[@BotFather](https://t.me/BotFather) → `/newbot` → copy the **token**. Use a **new bot** (Telegram
allows one active Trigger per bot).

### 3. Get a free Google Gemini API key

[Google AI Studio](https://aistudio.google.com/app/apikey) → *Create API key*. In n8n, create a
**Google Gemini (PaLM) API** credential. (Use `gemini-2.5-flash` — the free tier for `gemini-2.0-flash`
can be 0.)

### 4. Import & wire both workflows

1. Import `vps-snapshot-subworkflow.json` first, then `telegram-vps-devops-agent.json`.
2. **Credentials:** Telegram Trigger → your bot; the three SSH nodes → your VPS SSH key;
   Google Gemini Chat Model → your Gemini key.
3. **Token for sends:** open the **TG send** node and put your bot token in the URL —
   `https://api.telegram.org/bot<YOUR_TOKEN>/sendMessage`.
4. **Allowlist:** in the **Guard** node, set `ALLOWED_CHAT_ID` to your numeric chat id
   (from [@userinfobot](https://t.me/userinfobot)).
5. **Tool link:** open **get_vps_status** → Workflow → select the snapshot sub-workflow.
6. **Activate** the main workflow.

> If the bot stops receiving after publishing, toggle **Unpublish → Publish** once to re-register
> the Telegram webhook.

### 5. Use it

Send `/menu` for buttons, or just chat: *"¿cómo va el servidor?"*. Control buttons ask to confirm
before doing anything.

---

## Configuration reference

| Placeholder | Where | Replace with |
|---|---|---|
| `ALLOWED_CHAT_ID = 0` | Guard node | Your numeric Telegram chat id |
| `REPLACE_BOT_TOKEN` | TG send node URL | Your bot token |
| `REPLACE_WITH_SUBWORKFLOW_ID` | get_vps_status | Auto-set when you pick the sub-workflow |
| `REPLACE_ME` (credential ids) | various | Resolved when you map credentials |
| `models/gemini-2.5-flash` | Gemini node | Any model your key can access |

Callback scheme (in case you extend it): `r:*` reads, `c:nginx|c:n8n|c:mariadb` → confirm,
`c:unban` → list banned IPs, `ok:*` → execute, `x` → cancel.

---

## Security

- **Allowlist by chat id** — the bot ignores everyone but you. It controls your server.
- **Confirmation gate** — every control action requires an explicit *Confirm* tap.
- **Least privilege** — runs as the dedicated `vertiguard` user, limited to `/opt/vertiguard/*.sh`.
  Control scripts are small and fixed (restart a service, unban a validated IP) — nothing destructive.
- **Sanitized** — no real hosts, tokens, keys, or chat ids in this repo.

## License

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
