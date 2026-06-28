# Telegram personal assistant (n8n + Gemini)

A small family of **n8n** workflows that turn a Telegram bot into a personal assistant: a morning
**email digest**, a **calendar agenda**, an AI **news/RSS digest**, an **expense logger**, and a
**read-it-later** that summarizes any link you send it. AI runs on **Google Gemini** (free tier);
expenses and saved links go to **Google Sheets**.

> 🇪🇸 [Versión en español](README.es.md)

Each workflow is independent — import only the ones you want. They all ship **inactive**
(`"active": false`) so nothing runs until you review it.

---

## What's inside

| File | What it does | Trigger | Stack |
|---|---|---|---|
| [`workflows/a15-email-daily-digest.json`](workflows/a15-email-daily-digest.json) | Every morning, summarizes your last-24h inbox into a Telegram digest grouped by *needs reply / FYI / noise*. | Schedule (08:00) | Gmail · Gemini · Telegram |
| [`workflows/a16-calendar-daily-digest.json`](workflows/a16-calendar-daily-digest.json) | Sends today's agenda plus your free gaps during working hours. | Schedule (07:30) | Google Calendar · Telegram |
| [`workflows/a10-rss-ai-digest.json`](workflows/a10-rss-ai-digest.json) | Reads your RSS/Atom feeds and sends an AI-picked morning news digest. | Schedule (08:00) | RSS · Gemini · Telegram |
| [`workflows/a17-expense-logger.json`](workflows/a17-expense-logger.json) | Text `12 lunch` and it logs a row; text `/mes` for a monthly total by category. | Telegram message | Telegram · Google Sheets |
| [`workflows/a18-read-it-later.json`](workflows/a18-read-it-later.json) | Send a link and it fetches the page, summarizes it, saves it, and replies with the summary. | Telegram message | Telegram · HTTP · Gemini · Google Sheets |

---

## How they fit together

```
Scheduled (push to you)                 On-demand (you message the bot)
─────────────────────────               ──────────────────────────────
A15  inbox  ─┐                           A17  "12 lunch"  ─▶ Sheet row + ✓
A16  agenda ─┼─▶ Telegram each morning   A17  "/mes"      ─▶ monthly total
A10  news   ─┘                           A18  <link>      ─▶ summary + Sheet row
```

The three **scheduled** digests (A15, A16, A10) push to you on a timer — they can all share one bot.
The two **interactive** workflows (A17, A18) listen for your messages.

> ⚠️ **One active Telegram trigger per bot.** Telegram only delivers updates to a single active
> webhook per bot token. A17 and A18 each use a Telegram *trigger*, so they cannot both be active on
> the **same** bot at once. Options: give each its own bot, or merge them into one workflow that
> routes by message content (link → A18, otherwise → A17). The scheduled digests don't use a Telegram
> trigger, so they never collide.

---

## Setup

### 1. Credentials you'll need (only for the workflows you use)

| Credential (n8n type) | Used by | Notes |
|---|---|---|
| **Telegram** (`telegramApi`) | all | Bot token from [@BotFather](https://t.me/BotFather). |
| **Google Gemini** (`googlePalmApi`) | A15, A10, A18 | Free API key from [Google AI Studio](https://aistudio.google.com/). Model `models/gemini-2.5-flash`. |
| **Gmail** (`gmailOAuth2`) | A15 | Or swap for an IMAP node (see below). |
| **Google Calendar** (`googleCalendarOAuth2Api`) | A16 | |
| **Google Sheets** (`googleSheetsOAuth2Api`) | A17, A18 | |

### 2. Import & map

n8n → **Workflows → Import from File** → pick a `*.json`. Map each node's credential, then replace
the placeholders below.

### 3. Replace the placeholders

| Placeholder | Where | Replace with |
|---|---|---|
| `YOUR_CHAT_ID` | Telegram nodes / guard code | Your numeric chat id (from [@userinfobot](https://t.me/userinfobot)). |
| `YOUR_CALENDAR_ID` | A16 — *Today's events* | `primary`, or your calendar's id. |
| `YOUR_SHEET_ID` | A17, A18 — Sheets nodes | The id from your spreadsheet URL. |
| `REPLACE_ME` (credential ids) | every credentialed node | Auto-resolved when you map credentials. |
| example feed URLs | A10 — *Feed list* | Your own RSS/Atom feeds. |

### 4. Activate

Activate the workflow. For the scheduled ones, that's it. For A17/A18, message the bot to test.

---

## Per-workflow notes

**A15 — Email digest.** Uses the Gmail node with query `newer_than:1d -category:promotions
-category:social`. Prefer IMAP (IONOS, Zoho, your own server)? Replace the Gmail node with an
**Email Read (IMAP)** node and adjust the *Compile* code to read `from` / `subject` / `text`.

**A16 — Calendar.** Working window for free-gap detection is set in the *Format* code
(`WORK_START`/`WORK_END`, default 09:00–19:00). No AI required.

**A10 — RSS digest.** List your feeds in the *Feed list* code node. Items older than 24h are dropped;
the model picks the 5–8 most relevant. A failing feed is skipped (`continueRegularOutput`).

**A17 — Expenses.** Parses messages like `12 lunch`, `12€ lunch`, `lunch 12,50`. First word of the
description becomes the category. `/mes` reads the sheet and replies with the month's total by
category. Create a sheet/tab named `Expenses` with columns `Date, Amount, Currency, Category, Note`.

**A18 — Read-it-later.** Fetches the page over HTTP, strips it to ~6000 chars of text, and asks Gemini
for a summary + key points + tags. Saved to a tab named `Reading list`
(`Date, Title, URL, Summary`). Client-side-rendered pages (heavy JS) may yield little text — that's a
known limitation of plain HTTP fetching.

---

## Security

- **Sanitized** — no real tokens, chat ids, sheet ids, hosts, or feeds in this repo, only
  placeholders.
- Interactive workflows (A17, A18) **allowlist a single chat id** so only you can use them.
- Secrets live only in n8n credentials, never in the workflow JSON.

## License

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
