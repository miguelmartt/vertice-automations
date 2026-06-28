# Contact form (email) → Telegram

Get an instant **Telegram** alert whenever someone submits the contact form on your website —
**without touching your site's code**. The form already emails you; this workflow watches that
mailbox over **IMAP** and pings you the moment a matching email arrives.

> 🇪🇸 [Versión en español](README.es.md)

Ideal when your site (Laravel, WordPress, a static form service, anything) sends form submissions to
a mailbox but you don't want to wire a webhook into the site itself.

---

## How it works

```
Website contact form
   │  (sends an email to your mailbox)
   ▼
IMAP mailbox ─▶ Is it a form email? ─▶ Format alert ─▶ Notify Telegram
(only new mail,    (subject filter,        (from +          (to your chat)
 matching subject)  safety net)             subject + body)
```

- The **IMAP** trigger only fetches **unseen** mail whose subject contains your keyword
  (`["UNSEEN", ["SUBJECT", "SUBJECT_KEYWORD"]]`), so it ignores everything else in the inbox.
- A **Filter** node double-checks the subject as a safety net.
- A **Code** node builds a clean plain-text message (sender, subject, body).
- A **Telegram** node sends it to your chat. The trigger is IMAP, not Telegram, so it does **not**
  use up your bot's single active-trigger slot — reuse any existing bot.
- Matching mail is marked **read** after processing, so you're never notified twice.

One workflow:

| File | Role |
|---|---|
| [`workflows/form-email-to-telegram.json`](workflows/form-email-to-telegram.json) | IMAP → filter → format → Telegram |

Ships **inactive** (`"active": false`).

---

## Setup

### 1. Create an IMAP credential in n8n

**Credentials → IMAP**, with your mail provider's settings. For example (IONOS):

| Field | Value |
|---|---|
| Host | `imap.your-provider.com` (IONOS: `imap.ionos.es`) |
| Port | `993` |
| SSL/TLS | on |
| User | the mailbox that receives the form emails |
| Password | that mailbox's password |

### 2. Import the workflow

n8n → **Workflows → Import from File** → `workflows/form-email-to-telegram.json`.

### 3. Replace the placeholders

| Placeholder | Where | Replace with |
|---|---|---|
| `SUBJECT_KEYWORD` | **IMAP mailbox** (`customEmailConfig`) **and** **Is it a form email?** (Filter) | A word that always appears in your form emails' subject (e.g. `Contact`, `New lead`) |
| `YOUR_CHAT_ID` | **Notify Telegram** | Your numeric Telegram chat id (from [@userinfobot](https://t.me/userinfobot)) |
| `REPLACE_ME` (credential ids) | IMAP + Telegram nodes | Auto-resolved when you map credentials |

### 4. Map credentials & activate

Map the **IMAP** node to your mailbox credential and the **Telegram** node to your bot credential,
then **activate** the workflow. Submit your form once to test.

---

## Hardening (optional, recommended)

Instead of watching `INBOX`, create a **filter/rule in your mail provider** that moves form emails to
a dedicated folder (e.g. `Leads`), then set the IMAP node's `mailbox` to that folder. The workflow
then never touches your main inbox, and the subject filter becomes optional.

---

## Notes

- The alert is sent as **plain text** (no `parse_mode`) on purpose, so form content with `_` or `*`
  can't break Telegram's Markdown parser.
- Long submissions are trimmed to ~1500 characters.
- Works with any provider that offers IMAP (IONOS, Gmail, Zoho, Fastmail, your own server…).

## Security

- **Sanitized** — no real hosts, mailboxes, tokens, or chat ids in this repo, only placeholders.
- Your mailbox password lives only in the n8n credential, never in the workflow JSON.

## License

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
