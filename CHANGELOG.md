# Changelog

All notable changes to **vertice-automations** are documented here.
Format loosely based on [Keep a Changelog](https://keepachangelog.com/). Dates are ISO (YYYY-MM-DD).

> 🇪🇸 Registro de cambios del repo. Cada entrada resume qué se añadió o cambió.

## [Unreleased]

- Planned: RSS → AI digest template, expense logger, read-it-later.

## 2026-06-28 — Contact form → Telegram

### Added
- New template **`form-email-to-telegram`**: instant Telegram alert when a website contact form is
  submitted. Watches the mailbox over IMAP (filtered by subject), formats the sender/subject/body,
  and notifies a Telegram chat — no changes to the website needed. Bilingual docs (EN/ES), ships
  inactive.

## 2026-06-29 — Telegram VPS DevOps agent

### Added
- New template **`telegram-vps-devops-agent`**: run your VPS from Telegram.
  - Free-text chat backed by an AI agent (Google Gemini) with conversation memory and a
    `get_vps_status` tool that fetches a live snapshot over SSH.
  - **`/menu`** button interface: read status (services, disk, RAM, uptime, SSL, fail2ban, backups)
    and run **control actions** (restart nginx / n8n / MariaDB, unban an IP).
  - Every control action is gated by an explicit **Confirm / Cancel** step; access restricted to a
    single allowlisted chat id.
  - Inline keyboards sent via HTTP to the Telegram API for reliability across n8n versions.
  - Two workflows (main + snapshot sub-workflow), helper scripts, and bilingual docs (EN/ES).

## 2026-06-28 — Initial public release

### Added
- Repository scaffolding: MIT `LICENSE`, `CONTRIBUTING`, `.gitignore`, CI (`validate.yml`),
  bilingual root README (EN/ES), category-based `templates/` layout.
- Template **`vertiguard-vps-monitoring`** — the VertiGuard suite: 8 sanitized n8n workflows to
  monitor a self-hosted VPS (service health, disk/RAM, SSL expiry, backup watchdog, fail2ban report,
  external uptime, system updates, on-demand status) with Telegram alerts, plus an installer and
  helper scripts.
