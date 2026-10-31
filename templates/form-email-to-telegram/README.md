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
- Only emails **from your website** go through: sent from `FORM_FROM` and, by default, with a DKIM
  signature of that domain checked by your mailbox server (see [Checking the sender](#checking-the-sender)).
  Anyone can send you an email with the right subject; this keeps fakes out of your chat.
- Each match is turned into a short message and sent to your chat, then **marked as read**, so you
  are never notified twice.
- If you list the labels your form uses (`FIELDS=Name,Email,Phone`), it pulls those values out
  (`Name: Ana`, or the label on one line and the value on the next). `MESSAGE_START` /
  `MESSAGE_END` grab the free-text message. Without them, you get the subject and the body.
- Every email is handled on its own, so a broken one never holds up the rest. One that is too big
  (over 5 MB, never downloaded) or can't be read gets a short notice with its subject instead; one
  that does not come from your website is left out, with one message per check saying how many. Those
  emails stay unread in the mailbox with the IMAP keyword `$FormFailed`, so they are not fetched
  again (on a server that does not take keywords, they are marked as read instead).
- At most 10 emails per check; the rest come on the next one. Link previews are off, and if Telegram
  asks to slow down, it waits as asked.
- If the mailbox can't be read several times in a row (`FAILURES_BEFORE_ALERT`, 5 by default), it
  tells you once, and again when it works. If it is Telegram that fails, the email waits for the next
  check.
- The IMAP server's certificate is verified, and the bot only sends messages, so you can reuse any
  bot you already have.

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
| `FORM_FROM` | required: the From address your website sends the form emails with; `any` = every sender (not recommended) |
| `DKIM_DOMAIN` | the domain whose DKIM signature must pass; empty = the domain of `FORM_FROM`, `off` = no DKIM check |
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

The service runs as its own user with systemd hardening (`ProtectSystem=strict`, `NoNewPrivileges`,
no capabilities, a system call filter, only IP and local sockets…) and caps of 256 MB of memory and
half a CPU; it needs nothing but network access.

### Checking the sender

Open one of your form emails in your mail client and look at its source ("Show original", "View
source"). The **first** `Authentication-Results:` line is the one your mailbox server added, and it
should say `dkim=pass` with `header.d=example.com` (or `header.i=@example.com`), your domain. Only
that first line counts: any further down came with the email, and the sender could have written them.

- If it does, set `FORM_FROM` to the address in the email's `From:` and leave `DKIM_DOMAIN` empty (or
  set it to the `header.d` domain if it is not the one in `FORM_FROM`).
- If there is no such line, or it does not pass, your website sends without DKIM. Turn DKIM on for your
  domain at your email provider if you can; until then, `DKIM_DOMAIN=off` checks only `FORM_FROM`,
  which anyone can fake.

Emails that fail the check stay unread in the mailbox, and the bot says how many were left out.

## Update

```bash
cd vertice-automations && git pull && sudo bash templates/form-email-to-telegram/install.sh
```

From a release before the 2026-10-31 hardening: `FORM_FROM` is now required. Until it is in your
settings file, the installer updates the code but does not restart the service (the old one keeps
running); set it, check `DKIM_DOMAIN`, and run `systemctl restart form-to-telegram`.

The n8n version of this template is kept in the
[`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final) tag.

## Tests

```bash
cd templates/form-email-to-telegram && python3 -m unittest discover -s tests -t .
```
