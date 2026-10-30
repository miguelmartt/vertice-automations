# Contact form (email) → Telegram

Get a **Telegram** message the moment someone submits the contact form on your website —
**without touching your site's code**. The form already emails you; this small service watches that
mailbox over **IMAP** and forwards each new form email to your chat.

Python 3.9+, standard library only, run by systemd.

> 🇪🇸 [Versión en español](README.es.md)

---

## How it works

```
Website form ──email──▶ your mailbox ◀──IMAP every 60 s── form-to-telegram ──▶ Telegram
```

- Every `CHECK_EVERY_SECONDS` it looks for **unread** emails whose subject contains
  `SUBJECT_KEYWORD`, so the rest of the inbox is ignored.
- Each match is turned into a short message and sent to your chat, then **marked as read**, so you
  are never notified twice.
- If you list the labels your form uses (`FIELDS=Name,Email,Phone`), it pulls those values out
  (`Name: Ana`, or the label on one line and the value on the next). `MESSAGE_START` /
  `MESSAGE_END` grab the free-text message. Without them, you get the subject and the body.
- If the mailbox can't be read several times in a row (`FAILURES_BEFORE_ALERT`, 5 by default), it
  tells you once, and again when it works.
- The bot only sends messages, so you can reuse any bot you already have.

Example of what arrives:

```
📬 New contact from example.com

Name: Ana López
Email: ana@example.com
Phone: 600 000 000

💬 Message:
I'd like a quote for a new website.
```

---

## Install

```bash
git clone https://github.com/miguelmartt/vertice-automations.git
cd vertice-automations
sudo bash templates/form-email-to-telegram/install.sh
```

Then edit `/etc/form-to-telegram/form-to-telegram.env`:

| Setting | Meaning |
|---|---|
| `TELEGRAM_CHAT_ID`, `BOT_TOKEN` | your chat ID ([@userinfobot](https://t.me/userinfobot)) and a bot from [@BotFather](https://t.me/BotFather) |
| `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_FOLDER` | the mailbox that receives the form emails (IMAP over SSL, port 993) |
| `SUBJECT_KEYWORD` | text the form emails have in their subject (plain ASCII works best) |
| `SITE_NAME` | optional, shown in the title |
| `FIELDS` | optional, comma-separated labels to pull out, in order |
| `MESSAGE_START`, `MESSAGE_END` | optional, lines where the free-text message starts and ends |
| `LANGUAGE` | `en` or `es` |
| `CHECK_EVERY_SECONDS`, `FAILURES_BEFORE_ALERT` | how often to check, and when to complain |

Start it and send yourself a test through the form:

```bash
sudo systemctl enable --now form-to-telegram
journalctl -u form-to-telegram -f
```

The service runs as its own user with systemd hardening (`ProtectSystem=strict`,
`NoNewPrivileges`); it needs nothing but network access.

## Update

```bash
cd vertice-automations && git pull && sudo bash templates/form-email-to-telegram/install.sh
```

The n8n version of this template is kept in the
[`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final) tag.

## Tests

```bash
cd templates/form-email-to-telegram && python3 -m unittest discover -s tests -t .
```
