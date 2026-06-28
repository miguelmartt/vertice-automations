# Client / agency toolkit (n8n)

Three **n8n** workflows for freelancers and small agencies who run things for clients: a
**uptime monitor** for the sites you manage, an **invoice generator** (data → HTML → PDF → email),
and a **weekly analytics report** emailed to the client. No paid SaaS required — PDFs are rendered
with self-hostable [Gotenberg](https://gotenberg.dev/) and analytics come from
[Plausible](https://plausible.io/) / [Umami](https://umami.is/).

> 🇪🇸 [Versión en español](README.es.md)

Each workflow is independent — import only the ones you want. They all ship **inactive**
(`"active": false`) so nothing runs until you review it.

---

## What's inside

| File | What it does | Trigger | Stack |
|---|---|---|---|
| [`workflows/a12-client-uptime-monitor.json`](workflows/a12-client-uptime-monitor.json) | Checks a list of client sites every 5 min and sends a Telegram alert only when one is down or returns an error. | Schedule (5 min) | HTTP · Telegram |
| [`workflows/a13-invoice-pdf-generator.json`](workflows/a13-invoice-pdf-generator.json) | Turns invoice data into a styled HTML invoice, renders it to PDF with Gotenberg, and emails it to the client. | Manual / Webhook | Set · Gotenberg · SMTP |
| [`workflows/a14-weekly-analytics-report.json`](workflows/a14-weekly-analytics-report.json) | Every Monday, pulls visitors / pageviews / top pages / top sources from Plausible and emails an HTML report. | Schedule (weekly) | Plausible · SMTP |

---

## Setup

### 1. Credentials you'll need (only for the workflows you use)

| Credential (n8n type) | Used by | Notes |
|---|---|---|
| **Telegram** (`telegramApi`) | A12 | Bot token from [@BotFather](https://t.me/BotFather). |
| **SMTP** (`smtp`) | A13, A14 | Any SMTP account (your mail provider). |
| **Header Auth** (`httpHeaderAuth`) | A14 | Name = `Authorization`, Value = `Bearer YOUR_PLAUSIBLE_API_KEY`. |

A13 also needs a reachable **Gotenberg** instance (no credential — it's an internal HTTP service).
The quickest way: `docker run --rm -p 3000:3000 gotenberg/gotenberg:8`. If n8n and Gotenberg share a
Docker network, use the service name as host (e.g. `http://gotenberg:3000`).

### 2. Import & map

n8n → **Workflows → Import from File** → pick a `*.json`. Map each node's credential, then replace
the placeholders below.

### 3. Replace the placeholders

| Placeholder | Where | Replace with |
|---|---|---|
| `YOUR_CHAT_ID` | A12 — Telegram node | Your numeric chat id (from [@userinfobot](https://t.me/userinfobot)). |
| example site list | A12 — *Site list* code | Your clients' real URLs and labels. |
| `YOUR_GOTENBERG_HOST` | A13 — *HTML → PDF* node | Your Gotenberg host (e.g. `gotenberg` or `localhost`). |
| seller / client fields | A13 — *Invoice data* | Your company details and the line items. |
| `example.com` `client@example.com` | A13, A14 — Set nodes | Real site id and recipient. |
| `https://plausible.io` | A14 — *Config* | Keep for Plausible Cloud, or your self-hosted base URL. |
| `YOUR_PLAUSIBLE_API_KEY` | A14 — Header Auth credential | Plausible API key (Settings → API keys). |

### 4. Activate

Activate A12 and A14 (scheduled). A13 runs on demand — open it and **Execute**, or swap the manual
trigger for a Webhook / a "new row" trigger to wire it into your billing flow.

---

## Per-workflow notes

**A12 — Uptime monitor.** Edit the `SITES` array in the *Site list* code node. A request is treated
as **down** on HTTP ≥ 500 or no response (timeout/DNS), and as a **warning** on HTTP ≥ 400. Only
failures reach Telegram, so a healthy run is silent. Tune `SLOW_MS` / `TIMEOUT_MS` in the same node.
For per-site recovery notifications, pair it with the `vertiguard-vps-monitoring` patterns.

**A13 — Invoice generator.** The *Invoice data* node holds seller, client, tax rate, and an `items`
array (`desc`, `qty`, `price`). Totals and tax are computed in the *Render HTML* node, so the
template stays presentation-only — restyle the CSS freely. Gotenberg receives the HTML as
`index.html` and returns the PDF, which is attached to the email. No external API keys, nothing
leaves your infra. Prefer a hosted converter? Point the HTTP node at PDFShift/APITemplate instead.

**A14 — Weekly report.** Uses three Plausible Stats API calls (aggregate + two breakdowns). For a
**self-hosted Plausible**, only the base URL changes. For **Umami**, swap the endpoints/field names
(`/api/websites/{id}/stats` and `/metrics`) in the HTTP nodes and adjust `Format report` — the shape
is the same. The report is sent as HTML email; add the client's address in *Config*.

---

## Security

- **Sanitized** — no real tokens, chat ids, hosts, site ids, or API keys in this repo, only
  placeholders.
- Secrets live only in n8n credentials, never in the workflow JSON.
- A12's Telegram alert and A13/A14's emails go only where you configure them.

## License

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
