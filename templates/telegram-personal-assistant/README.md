# Telegram personal assistant

A small Python service that turns one Telegram bot into a personal assistant: a morning **email
digest**, **today's agenda** with your free slots, an AI **news digest** from your RSS feeds, an
**expense logger** and a **read-it-later** that summarizes any link you send it. AI runs on **Google
Gemini** (free tier); expenses and saved links go to **Google Sheets**.

Python 3.9+ standard library only, run by systemd, no open ports (the bot uses long polling).

> 🇪🇸 [Versión en español](README.es.md)

**Status:** ported from the n8n version on 2026-10-30. Covered by unit tests; not yet run against real
Google accounts. The old n8n workflows are kept in the
[`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final) tag.

---

## What it does

| Feature | When | Needs | What you get |
|---|---|---|---|
| Calendar agenda | every day, 07:30 | Google | Today's events and your free slots (30 min or more) in working hours. |
| Email digest | every day, 08:00 | Google + Gemini | Last 24 h of email grouped into *needs a reply / FYI / probably noise*. |
| News digest | every day, 08:00 | Gemini + feeds | The 5–8 most relevant headlines of the last 24 h from your RSS/Atom feeds. |
| Expense logger | you send `12 lunch` | Google + spreadsheet | A row in the `Expenses` tab; `/month` (or `/mes`) gives the month's total by category. |
| Read-it-later | you send a link | Google + spreadsheet + Gemini | The page summarized (summary, 3 key points, 3 tags), saved to the `Reading list` tab. |

Each feature turns itself on only when its settings are filled in, so you can start with just the
ones you want. At startup the journal says which features are on and what each of the others is
missing.

## How it works

One process, two threads:

```
scheduler thread                          main thread: Telegram long polling
────────────────                          ──────────────────────────────────
07:30 agenda   (Calendar)        ─┐       your message ─▶ only TELEGRAM_CHAT_ID is answered
08:00 email    (Gmail + Gemini)  ─┼─▶ Telegram        /month, /mes  ─▶ month's expenses
08:00 news     (RSS + Gemini)    ─┘                   other /command ─▶ help
                                                      has a link     ─▶ read-it-later
                                                      anything else  ─▶ expense (12 lunch)
```

- **Routing.** The old n8n version had two separate Telegram triggers (expenses and read-it-later)
  that could not share a bot. Here a single bot routes each message: a command first, then a link
  (the first `http(s)://` in the text or caption, or a link hidden behind formatted text), and
  anything else is read as an expense. `12 https://example.com` is therefore a link, not an expense.
  A message without an amount gets a hint.
- **Expenses.** `12 lunch`, `12€ lunch`, `lunch 12,50`, `$12 taxi`, `15 usd taxi`: the first number is
  the amount; `€`, `eur`, `euros`, `$` or `usd` before or after it set the currency (else
  `EXPENSE_CURRENCY`); the rest of the text is the note, and its first word, in lowercase, the
  category. The date is today's in your time zone.
- **Digests.** Mail is read with the Gmail search `EMAIL_QUERY` (by default the last day, without
  promotions or social). Feed items older than 24 h are dropped (if nothing is that recent, the
  latest items are used); a feed that fails is skipped. When there is no mail or no news, you get a
  short "nothing new" message and Gemini is not called.
- **Failures.** If a digest fails (Google down, a revoked token, every feed unreachable...) you get
  one Telegram message, and another one when it works again; never one per run. If a message cannot
  be handled, the bot answers with the error.
- **Restarts.** The Telegram offset is saved in `/var/lib/personal-assistant/state.json`, so a restart
  never handles the same message (or logs the same expense) twice.
- **Pages** are downloaded with plain HTTP (up to 2 MB), scripts and styles are dropped and the first
  6,000 characters of text go to Gemini. Pages that need JavaScript may give little or no text; the
  link is saved anyway, with an empty summary.

## Setup

You need a Linux server with systemd and Python 3.9 or newer (stock AlmaLinux 9 or Debian 11 and
later are fine), able to reach HTTPS sites. For Google, also a computer with a web browser and Python
for the one-time authorization.

### 1. Install

```bash
git clone https://github.com/miguelmartt/vertice-automations.git
cd vertice-automations/templates/telegram-personal-assistant
sudo bash install.sh
```

It creates the `personal-assistant` system user, the code in `/opt/personal-assistant`, the config in
`/etc/personal-assistant/personal-assistant.env` (mode 640, never overwritten if it exists) and the
systemd unit. It does not start the service the first time.

### 2. Telegram bot and chat ID

1. Talk to [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token into
   `TELEGRAM_BOT_TOKEN`. Use a bot only for this assistant: a bot can only be read by one program
   at a time. (If the bot had a webhook, for example from n8n, the service removes it at startup.)
2. Send any message to your new bot, then open
   `https://api.telegram.org/botYOUR_TOKEN/getUpdates` in a browser and copy the number in
   `"chat":{"id":...}` into `TELEGRAM_CHAT_ID`. ([@userinfobot](https://t.me/userinfobot) tells you
   too.)

### 3. Gemini API key (email digest, news digest, read-it-later)

Create a free key in [Google AI Studio](https://aistudio.google.com/) (*Get API key*) and put it in
`GEMINI_API_KEY`.

### 4. Google account (email digest, agenda, expenses, read-it-later)

The assistant talks to Gmail, Calendar and Sheets with an OAuth client of your own:

1. In the [Google Cloud console](https://console.cloud.google.com/), create a project (for example
   `personal-assistant`).
2. **APIs & Services → Library**: enable **Gmail API**, **Google Calendar API** and **Google Sheets
   API** (only the ones you will use).
3. **Google Auth Platform** (the OAuth consent screen): click *Get started*, give it a name and your
   email, choose **External** as the audience (or *Internal* in a Google Workspace) and finish.
4. **Audience → Publish app**, so it is *In production*. While it is in *Testing*, Google expires the
   refresh token after 7 days. As the app is not verified, the consent page warns that "Google hasn't
   verified this app": it is your own app, so click *Advanced → Go to ... (unsafe)*.
5. **Clients → Create client**, type **Desktop app**, and download its JSON file.
6. On your computer (not the server), from this folder:

   ```bash
   python3 app/google_auth.py ~/Downloads/client_secret_XXXX.json
   ```

   Your browser opens Google's consent page; pick the account and allow access. The script catches
   the answer on `http://127.0.0.1:<random port>` and prints three lines (`GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`) to paste in the config. Without the JSON file, it
   asks for the client ID and secret. It asks for `gmail.readonly`, `calendar.readonly` and
   `spreadsheets`; to grant less, add for example `--scopes calendar,sheets`.

The refresh token gives access to those scopes of your account: keep it only in the config file. You
can revoke it at any time at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

### 5. Spreadsheet (expenses, read-it-later)

Create a Google Sheet in the account you authorized, with two tabs and these headers in row 1:

| Tab | A | B | C | D | E |
|---|---|---|---|---|---|
| `Expenses` | Date | Amount | Currency | Category | Note |
| `Reading list` | Date | Title | URL | Summary | |

The columns must be in that order (the header texts are not read). Put the ID from its URL
(`docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit`) in `SPREADSHEET_ID`. The tab names can be
changed with `EXPENSES_SHEET` and `READING_SHEET`. Values are written as plain values (dates as
`YYYY-MM-DD` text, amounts as numbers), never as formulas; `/month` adds the rows whose date starts
with the current `YYYY-MM`.

### 6. Start it

```bash
sudo nano /etc/personal-assistant/personal-assistant.env   # fill in what you use
sudo systemctl enable --now personal-assistant
journalctl -u personal-assistant -f
```

The first lines show what is on, for example:

```
INFO assistant: email digest: on, every day at 08:00
INFO assistant: calendar agenda: on, every day at 07:30
INFO assistant: news digest: off (not set: RSS_FEEDS)
INFO assistant: expense logger: on
INFO assistant: read-it-later: on
```

After changing the config: `sudo systemctl restart personal-assistant`.

## Settings

All in `/etc/personal-assistant/personal-assistant.env`, one `KEY=value` per line, no quotes. An empty
setting without a default turns its feature off.

| Setting | Default | Used by | What it is |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | (required) | all | Bot token from @BotFather. |
| `TELEGRAM_CHAT_ID` | (required) | all | The only chat the bot answers, and where the digests go. |
| `LANGUAGE` | `en` | all | `en` or `es`: messages and AI summaries. |
| `TIMEZONE` | server time | all | Time zone of the digest times and the sheet dates, like `Europe/Madrid`. |
| `GEMINI_API_KEY` | empty | email, news, read-it-later | Google AI Studio key. |
| `GEMINI_MODEL` | `gemini-flash-latest` | email, news, read-it-later | Gemini model. |
| `GOOGLE_CLIENT_ID` | empty | email, agenda, expenses, read-it-later | Desktop app OAuth client. |
| `GOOGLE_CLIENT_SECRET` | empty | email, agenda, expenses, read-it-later | Its secret. |
| `GOOGLE_REFRESH_TOKEN` | empty | email, agenda, expenses, read-it-later | Printed by `app/google_auth.py`. |
| `EMAIL_DIGEST_TIME` | empty (example: `08:00`) | email | Time to send it, `HH:MM`. |
| `EMAIL_QUERY` | `newer_than:1d -category:promotions -category:social` | email | Gmail search of the messages to summarize. |
| `EMAIL_MAX_MESSAGES` | `25` | email | Most messages to read. |
| `CALENDAR_DIGEST_TIME` | empty (example: `07:30`) | agenda | Time to send it, `HH:MM`. |
| `CALENDAR_ID` | `primary` | agenda | Calendar to read (`primary` or the ID in the calendar's settings). |
| `CALENDAR_WORK_START` | `09:00` | agenda | Start of the working hours for free slots. |
| `CALENDAR_WORK_END` | `19:00` | agenda | End of the working hours. |
| `NEWS_DIGEST_TIME` | empty (example: `08:00`) | news | Time to send it, `HH:MM`. |
| `RSS_FEEDS` | empty | news | Comma-separated feed URLs. |
| `SPREADSHEET_ID` | empty | expenses, read-it-later | The spreadsheet's ID. |
| `EXPENSES_SHEET` | empty (example: `Expenses`) | expenses | Tab of the expenses. |
| `EXPENSE_CURRENCY` | `€` | expenses | Currency when a message names none. |
| `READING_SHEET` | empty (example: `Reading list`) | read-it-later | Tab of the saved links. |

"Example" values are the ones in `personal-assistant.env.example`: they are the times of the old n8n
workflows, so the digests stay on if you keep them.

## Testing

Unit tests (no network, no accounts), from this folder:

```bash
python3 -m unittest discover -s tests -t .
```

They cover the message routing, expense parsing and monthly totals, RSS/Atom parsing, building the
three digests, the Google token refresh and caching, read-it-later's page text, and which features
turn on for each config.

On the server, once it runs, send the bot `/help`, `12 lunch`, `/month` and a link, and look at the
sheet. To try a digest without waiting for the morning, set its time a couple of minutes ahead,
restart the service and watch `journalctl -u personal-assistant -f`.

To try it on your computer instead, copy the example config, fill it in and run
`STATE_DIRECTORY=. python3 app/assistant.py my-test.env` (Ctrl+C stops it). Stop the server's
service first: only one program can read a bot's messages.

## Updating

```bash
git pull
sudo bash install.sh   # keeps your config and restarts the service if it is running
```

## Changes from the n8n version

- One bot for the expense logger and read-it-later, with the routing above (they used to need a bot
  each). `/month` works too, besides `/mes`, and `/help` lists what is on.
- Messages in English or Spanish (`LANGUAGE`); the AI summaries are written in that language.
- Expense fixes: `12 euros lunch` no longer leaves "os" in the note, `$12` is read as dollars, an
  expense without a description gets the category "(uncategorized)", and the date is the local one
  (n8n used the UTC date, so late-night expenses went to the previous day).
- No mail or no news: a fixed message instead of a Gemini call. Each digest starts with a title line.
- A page that cannot be read is saved with an empty summary instead of an AI-written "could not be
  read"; values go to Sheets as plain values, so a page title can never run as a formula.
- If no feed can be read, the news digest reports a failure instead of "nothing new".

## Security

- **Sanitized:** no real tokens, chat IDs, spreadsheet IDs or feeds in this repo, only placeholders.
- The bot answers a single chat ID and ignores everything else.
- Secrets live only in `/etc/personal-assistant/personal-assistant.env` (`640`, `root:personal-assistant`).
- Gmail and Calendar are read-only scopes; Sheets needs write access to add rows.
- The service runs as its own unprivileged user with a read-only view of the system (systemd
  hardening in `systemd/personal-assistant.service`).

## License

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
