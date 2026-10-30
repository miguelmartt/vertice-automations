# Client / agency toolkit

A small Python service for freelancers and small agencies who look after sites for clients. It
lives on your server, runs under systemd and needs nothing but Python 3.9+ (standard library only,
no `pip`):

- **Client uptime monitor**: checks your clients' sites every 5 minutes and tells you on Telegram
  when one goes down, starts returning errors, or comes back.
- **Weekly analytics report**: every Monday, visitors, pageviews, top pages and top sources from
  [Plausible](https://plausible.io/) (or [Umami](https://umami.is/)) in an HTML email to the client.
- **Invoice generator**: a command that turns invoice data (JSON) into a PDF with a self-hosted
  [Gotenberg](https://gotenberg.dev/) and emails it to the client.

No paid SaaS: PDFs are rendered on your own server and the stats come from your analytics.

> 🇪🇸 [Versión en español](README.es.md)

---

## How it works

| Feature | Runs | Needs |
|---|---|---|
| Uptime monitor | Inside the service, every `UPTIME_INTERVAL_MINUTES` (5) | Telegram bot |
| Weekly report | Inside the service, `REPORT_DAY` at `REPORT_TIME` (Monday 09:00) | Plausible or Umami API key, SMTP |
| Invoices | On demand: `python3 /opt/agency-toolkit/app/invoice.py invoice.json` | Gotenberg, SMTP |

- **One service**, `agency-toolkit`, run by systemd as its own system user. It reads
  `/etc/agency-toolkit/agency-toolkit.env` and schedules the uptime checks and the report.
- **Each feature turns itself off** while its settings are empty. At startup the service logs which
  ones are on and, for the others, which settings are missing (`journalctl -u agency-toolkit`).
- **Uptime**: no response (timeout, DNS, TLS error) or HTTP ≥ 500 is *down*, HTTP ≥ 400 is a
  *warning*, anything else is *up* (redirects are followed). You get **one alert per change**: when a
  site goes down, turns into a warning or recovers, never on every check. The last status of each
  site is saved in `/var/lib/agency-toolkit/state.json`, so a restart does not repeat an alert.
- **Report**: covers the last `REPORT_DAYS` (7) full days ending yesterday, so on a Monday it is the
  previous Monday to Sunday. It uses the Plausible Stats API (one aggregate call and two breakdowns)
  and sends an HTML email with a plain-text alternative.
- **Invoices**: totals are computed with exact decimals (each line rounded to cents, VAT on the
  subtotal, half up). The HTML template is `app/invoice_template.html`; restyle it freely.
- If a scheduled job starts failing (Plausible down, SMTP refusing the login...) you get a Telegram
  message, and another one when it works again. Once per change, not on every run.

## Setup

You need a Linux server with systemd and Python 3.9 or newer (AlmaLinux 9, Debian 11 or later and
Ubuntu 22.04 already have it). Set up only the parts you want to use.

### 1. Install

Copy this folder to the server (for example by cloning the repository) and run, as root:

```bash
cd templates/client-agency-toolkit
sudo bash install.sh
```

It creates the `agency-toolkit` system user, copies the code to `/opt/agency-toolkit`, creates
`/etc/agency-toolkit/agency-toolkit.env` from [`agency-toolkit.env.example`](agency-toolkit.env.example)
(only if it does not exist yet) and installs the systemd unit. It does not start anything. Run it
again after pulling changes to update the code; your config is kept.

### 2. Telegram bot (uptime alerts)

1. Talk to [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token into
   `TELEGRAM_BOT_TOKEN`.
2. Open a chat with your new bot and press **Start**, otherwise it cannot write to you.
3. Ask [@userinfobot](https://t.me/userinfobot) for your numeric ID and put it in
   `TELEGRAM_CHAT_ID`. For a group, add the bot to it and use the group's ID (it starts with `-`).

### 3. Sites to watch

```ini
UPTIME_SITES=Client A|https://example.com, Client B|https://shop.example.org, Client C|https://example.net/health
```

Each item is `Label|URL`, separated by commas. The label is what you see in the alert.

### 4. Plausible API key (weekly report)

In Plausible, go to your account settings > **API keys** > **New API key**, choose the Stats API,
and copy it into `PLAUSIBLE_API_KEY`. `PLAUSIBLE_SITE_ID` is the site's domain as it appears in
Plausible (`example.com`). Self-hosted Plausible: also set `PLAUSIBLE_URL` to your instance. On
Plausible Cloud, check that your plan includes the Stats API.

Put the client's address in `REPORT_TO` (several, comma-separated, are fine).

**Umami instead?** Set `ANALYTICS_PROVIDER=umami`, `UMAMI_API_URL` (`https://api.umami.is/v1` for
Umami Cloud, `https://umami.example.com/api` for self-hosted), `UMAMI_WEBSITE_ID` (Settings >
Websites > Edit) and either `UMAMI_API_KEY` or, for a self-hosted Umami without API keys,
`UMAMI_USERNAME` and `UMAMI_PASSWORD` (an account without two-factor). Bounce rate and average visit
duration are computed from Umami's visits, bounces and total time.

### 5. SMTP (report and invoices)

Any mailbox you can send from works. Fill in `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` and
`SMTP_FROM` (`Your Company <billing@example.com>`). `SMTP_SECURITY` is `starttls` (port 587, the
default), `ssl` (port 465) or `none` (a local relay on port 25, no login if `SMTP_USER` is empty).

### 6. Gotenberg (invoices)

Gotenberg turns the invoice HTML into a PDF. With Docker, one line, only reachable from the server
itself:

```bash
docker run -d --name gotenberg --restart unless-stopped -p 127.0.0.1:3000:3000 gotenberg/gotenberg:8
```

Then set `GOTENBERG_URL=http://127.0.0.1:3000`.

### 7. Start

```bash
sudo systemctl enable --now agency-toolkit
journalctl -u agency-toolkit -f
```

The first lines say which features are on. After editing the config:
`sudo systemctl restart agency-toolkit`.

## Invoices

Copy the example, fill it in, try it, send it:

```bash
cp /opt/agency-toolkit/invoice.example.json ~/invoice-2026-001.json
nano ~/invoice-2026-001.json
sudo python3 /opt/agency-toolkit/app/invoice.py ~/invoice-2026-001.json --dry-run
sudo python3 /opt/agency-toolkit/app/invoice.py ~/invoice-2026-001.json
```

`--dry-run` writes `invoice-2026-001.html` and `invoice-2026-001.pdf` next to the JSON and sends
nothing (without `GOTENBERG_URL` it writes only the HTML). Without it, the PDF is emailed to
`client_email`, from `SMTP_FROM`. `sudo` is there because the command reads the config file, which
only root and the service can read; `--config PATH` points it to another one.

| Field | Required | Notes |
|---|---|---|
| `invoice_number` | yes | Shown on the invoice, in the subject and in the PDF name. |
| `seller_name`, `seller_taxid`, `seller_address` | name | Your details. |
| `client_name`, `client_taxid`, `client_email` | name, email | `client_email` is where it is sent. |
| `items` | yes | Lines with `desc`, `qty` and `price` (numbers or strings like `"49.95"`). |
| `tax_rate` | no | VAT percentage, for example `21`. Default `0`. |
| `currency` | no | ISO code, default `EUR`. |
| `date` | no | `YYYY-MM-DD`; today if missing. |
| `language` | no | `en` or `es` for this invoice; default `LANGUAGE`. |

Every value is HTML-escaped before it goes into the template.

## Settings

All of them live in `/etc/agency-toolkit/agency-toolkit.env`, one `KEY=value` per line, values
without quotes. Empty means "not set".

| Setting | Default | What it does |
|---|---|---|
| `LANGUAGE` | `en` | `en` or `es`: alerts, report and invoices. |
| `TIMEZONE` | server's | Time zone of the report schedule and dates, like `Europe/Madrid`. |
| `TELEGRAM_BOT_TOKEN` | | Bot token from @BotFather. |
| `TELEGRAM_CHAT_ID` | | Chat that receives the alerts. |
| `UPTIME_SITES` | | `Label\|URL` items, comma-separated. Empty: monitor off. |
| `UPTIME_INTERVAL_MINUTES` | `5` | Minutes between checks. |
| `UPTIME_TIMEOUT_SECONDS` | `10` | Seconds to wait before counting a site as down. |
| `REPORT_TO` | | Report recipients, comma-separated. Empty: report off. |
| `REPORT_SITE_NAME` | site ID | Name in the subject and heading. |
| `REPORT_DAY` | `monday` | Day to send the report. |
| `REPORT_TIME` | `09:00` | Local time to send it. |
| `REPORT_DAYS` | `7` | Full days covered, ending yesterday. |
| `ANALYTICS_PROVIDER` | `plausible` | `plausible` or `umami`. |
| `PLAUSIBLE_URL` | `https://plausible.io` | Your instance if self-hosted. |
| `PLAUSIBLE_SITE_ID` | | Site domain in Plausible. |
| `PLAUSIBLE_API_KEY` | | Stats API key. |
| `UMAMI_API_URL` | | API root: `https://api.umami.is/v1` or `https://umami.example.com/api`. |
| `UMAMI_WEBSITE_ID` | | Website ID (UUID). |
| `UMAMI_API_KEY` | | API key... |
| `UMAMI_USERNAME`, `UMAMI_PASSWORD` | | ...or a login, for self-hosted Umami without API keys. |
| `GOTENBERG_URL` | | Gotenberg base URL. Empty: invoices off. |
| `SMTP_HOST` | | SMTP server. Empty: report and invoices off. |
| `SMTP_SECURITY` | `starttls` | `starttls`, `ssl` or `none`. |
| `SMTP_PORT` | 587 / 465 / 25 | Depends on `SMTP_SECURITY`. |
| `SMTP_USER`, `SMTP_PASSWORD` | | SMTP login; empty user = no login. |
| `SMTP_FROM` | | Sender, like `Your Company <billing@example.com>`. |

## How to test it

**Unit tests** (no network, no accounts; fake Telegram, HTTP, SMTP and Gotenberg):

```bash
cd templates/client-agency-toolkit
python3 -m unittest discover -s tests -t .
```

**On the server**, once it is configured:

- **Uptime**: add `Test|https://example.invalid` to `UPTIME_SITES` and restart. Within 5 minutes you
  get a "not responding" alert, and nothing more on the next checks. Remove it afterwards.
- **Report**: `sudo python3 /opt/agency-toolkit/app/report.py --dry-run > /tmp/report.html` fetches
  the real numbers and writes the email's HTML without sending it. Without `--dry-run` it emails the
  report now.
- **Invoices**: the `--dry-run` above, then open the PDF.

**Without installing it** (on your laptop, for example): copy `agency-toolkit.env.example` to
`my.env`, fill it in, and run `mkdir -p /tmp/agency-toolkit && STATE_DIRECTORY=/tmp/agency-toolkit
python3 app/toolkit.py my.env`. `report.py` and `invoice.py` take `--config my.env`.

## Notes

- **Sites behind Cloudflare or a WAF** may answer the checker with 403 (a warning). The checker
  sends the User-Agent `Mozilla/5.0 (compatible; agency-toolkit uptime monitor)`; allow it, or check
  a health URL that is not challenged.
- The report uses the **Plausible Stats API v1** (`/api/v1/stats/aggregate` and `/breakdown`), the
  same calls as the n8n version.
- For Umami, pages are read with the metric type `path` (Umami 3) and, if the server rejects it,
  `url` (older versions).

## Changes from the n8n version

This replaces the three n8n workflows (A12, A13, A14), which are kept in the git tag `n8n-final`.

- **Uptime (A12)**: one alert per status change, plus a recovery message (A12 repeated the alert
  every 5 minutes while a site was down and never said when it came back). The site list moved to the
  config file. A12's per-site `expectStatus` and its `SLOW_MS` setting (defined but never used) are
  gone.
- **Report (A14)**: sent at 09:00 instead of 08:00. The period is the explicit last 7 full days
  (Plausible `custom` range) instead of Plausible's `7d`, so the email shows the dates. Umami is
  built in instead of being a manual edit. The email has a plain-text part, and the four stat cards
  are a table so that more email clients show them side by side.
- **Invoices (A13)**: a command reading a JSON file instead of a manual trigger with a Set node. The
  PDF is A4 with backgrounds printed (Gotenberg's defaults are US Letter and no backgrounds, which
  would leave the white text of the table header on white). Labels follow `LANGUAGE`, and amounts
  use exact decimals.

## Status

Ported from the n8n version on 2026-10-30. Covered by unit tests; not yet run against real
Plausible, Umami, Gotenberg or SMTP accounts.

## Security

- Secrets live only in `/etc/agency-toolkit/agency-toolkit.env` (mode `640`, `root:agency-toolkit`).
  Nothing in this folder is real: only placeholders.
- The service needs no open port: it only makes outgoing requests. Keep Gotenberg bound to
  `127.0.0.1`.
- The systemd unit runs as an unprivileged user with a read-only view of the system (it can only
  write `/var/lib/agency-toolkit`).

## License

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
