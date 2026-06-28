# vertice-automations

Reusable **n8n** workflow templates — ready to import, documented, and safe to self-host.
Maintained by [Vérticedev](https://verticedev.es). Licensed under [MIT](LICENSE).

> 🇪🇸 ¿Prefieres español? Lee el [README en español](README.es.md).

---

## What's inside

Each automation lives in its own self-contained folder under [`templates/`](templates/), with its
workflow JSON(s), any helper scripts, and its own README. Pick the ones you need.

| Template | What it does | Stack |
|---|---|---|
| [`vertiguard-vps-monitoring`](templates/vertiguard-vps-monitoring/) | **VertiGuard** — an 8-workflow suite to monitor a self-hosted VPS (services, disk/RAM, SSL, backups, fail2ban, system updates, external uptime, on-demand `/status`) and alert via Telegram. | n8n · SSH · Telegram |
| [`telegram-vps-devops-agent`](templates/telegram-vps-devops-agent/) | Run your VPS from Telegram — chat with an AI agent (Gemini) or use a `/menu` of buttons to read status and run control actions (restart services, unban IP) with a Confirm step. Reuses the VertiGuard scripts. | n8n · LangChain · Gemini · SSH · Telegram |
| [`form-email-to-telegram`](templates/form-email-to-telegram/) | Get an instant Telegram alert when someone submits your website's contact form — watches the mailbox over IMAP, no changes to your site. | n8n · IMAP · Telegram |
| [`telegram-personal-assistant`](templates/telegram-personal-assistant/) | Five Telegram assistant workflows: morning email digest, calendar agenda, AI news/RSS digest, expense logger, and a read-it-later that summarizes any link. AI on Gemini; data in Google Sheets. | n8n · Gemini · Gmail · Calendar · Sheets · Telegram |

_More templates are added over time._

---

## How to use a template

1. Open the template folder and read its README.
2. In n8n: **Workflows → Import from File** and select the `*.json` you want.
3. Map the credentials the workflow asks for (e.g. an SSH key, a Telegram bot token).
4. Replace the placeholders (see each template's README) and activate.

All workflows ship **inactive** (`"active": false`) so nothing runs until you review it.

---

## Placeholders & security

These templates are **sanitized**. They contain no real hosts, IPs, tokens, chat IDs, or keys —
only placeholders you fill in:

| Placeholder | Replace with |
|---|---|
| `YOUR_CHAT_ID` | Your Telegram chat ID |
| `REPLACE_ME` (credential id) | Auto-resolved when you map credentials in n8n |
| `example.com`, `n8n.example.com` | Your own domains (script variables) |
| `b2:my-backups` | Your own rclone remote/path |

Secrets never belong in the repo: `.gitignore` blocks keys, `.env`, and credential files by default.
Security does **not** depend on these workflows being private — your real protection is SSH keys,
fail2ban, and your firewall, none of which are published here.

---

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Keep contributions sanitized (no real secrets)
and ship workflows inactive.

## License

[MIT](LICENSE) © Vérticedev
