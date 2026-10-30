# vertice-automations

Self-hosted automations that live on your own server: small **Python services run by systemd**,
with no automation platform in between, nothing to `pip install` and no monthly fees.
Maintained by [Vérticedev](https://verticedev.es). Licensed under [MIT](LICENSE).

> 🇪🇸 ¿Prefieres español? Lee el [README en español](README.es.md).

---

## What's inside

Each automation lives in its own self-contained folder under [`templates/`](templates/), with its
code, tests, installer, systemd unit, example settings and README. Pick the ones you need.

| Template | What it does | Talks to |
|---|---|---|
| [`vertiguard`](templates/vertiguard/) | **VertiGuard** — watches a VPS (services, websites, disk/RAM, SSL, backups, fail2ban, updates) and alerts on Telegram only when something changes. Includes a DevOps bot (`/menu` buttons with confirmed actions, plus Gemini chat) and an UptimeRobot webhook. | Telegram · Gemini · UptimeRobot |
| [`form-email-to-telegram`](templates/form-email-to-telegram/) | Instant Telegram message when someone submits your website's contact form — watches the mailbox over IMAP, no changes to your site. | IMAP · Telegram |
| [`telegram-personal-assistant`](templates/telegram-personal-assistant/) | A personal assistant on Telegram: morning email digest, today's agenda, an AI-picked news digest from your RSS feeds, an expense logger and a read-it-later that summarizes any link. | Gmail · Calendar · Sheets · Gemini · Telegram |
| [`client-agency-toolkit`](templates/client-agency-toolkit/) | For freelancers and agencies: client-site uptime monitor, invoice generator (JSON → HTML → PDF → email) and a weekly analytics report by email. | Plausible · Gotenberg · SMTP · Telegram |

---

## Why plain Python services

These started as n8n workflows. Running them as code turned out simpler to operate:

- **Light.** A template uses a few tens of MB of RAM; there is no platform, database or editor to
  keep running and updated.
- **Reviewable.** Every change is a diff in git, with tests. Nothing hides in a JSON export.
- **Safer.** No web panel holding all your credentials. Each service runs as its own system user,
  talks to Telegram by long polling (no open ports) and keeps its secrets in one root-owned file.
- **Portable.** Python 3.9+ standard library only: it runs on a stock AlmaLinux 9, Debian or Ubuntu
  server.

The n8n versions are kept in the [`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final)
tag if you still want them.

---

## How to use a template

```bash
git clone https://github.com/miguelmartt/vertice-automations.git
cd vertice-automations
sudo bash templates/<template>/install.sh
```

Then fill in `/etc/<service>/<service>.env` as the template's README explains and start it with
`systemctl enable --now <service>`. Re-running the installer after a `git pull` updates the code and
keeps your settings. Logs: `journalctl -u <service> -f`.

---

## Security

The templates are **sanitized**: no real hosts, IPs, tokens, chat IDs or keys, only placeholders
(`YOUR_CHAT_ID`, `REPLACE_ME`, `example.com`). Your secrets go in `/etc/<service>/<service>.env`
(mode `640`, readable by the service user only) and never in the repo; `.gitignore` blocks `.env`
files and keys. Where root access is needed (VertiGuard's probes), it goes through one narrow
`sudo` rule for a fixed set of scripts.

---

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the layout and conventions every template
follows.

## License

[MIT](LICENSE) © Vérticedev
