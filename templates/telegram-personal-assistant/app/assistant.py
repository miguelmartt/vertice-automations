"""Telegram personal assistant: morning digests (email, calendar, news) and one bot that logs expenses and
saves links with a summary. Each feature turns itself on only when its settings are filled in.

Usage: assistant.py /etc/personal-assistant/personal-assistant.env
"""

import logging
import os
import sys
import threading
import zoneinfo
from datetime import datetime

import config
import digests
import gemini
import google
import messages
import scheduler
import state
import telegram
from bot import Bot
from expenses import Expenses
from reading import ReadItLater

log = logging.getLogger("assistant")

GOOGLE_KEYS = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
DEFAULT_EMAIL_QUERY = "newer_than:1d -category:promotions -category:social"

# Feature -> name in the logs.
FEATURES = {
    "email": "email digest",
    "calendar": "calendar agenda",
    "news": "news digest",
    "expenses": "expense logger",
    "reading": "read-it-later",
}


def missing_settings(cfg):
    """For each feature, the settings it still needs. A feature is on when that list is empty."""
    def need(*keys):
        return [key for key in keys if not cfg.get_str(key)]

    return {
        "email": need("EMAIL_DIGEST_TIME", "GEMINI_API_KEY", *GOOGLE_KEYS),
        "calendar": need("CALENDAR_DIGEST_TIME", *GOOGLE_KEYS),
        "news": need("NEWS_DIGEST_TIME", "RSS_FEEDS", "GEMINI_API_KEY"),
        "expenses": need("SPREADSHEET_ID", "EXPENSES_SHEET", *GOOGLE_KEYS),
        "reading": need("SPREADSHEET_ID", "READING_SHEET", "GEMINI_API_KEY", *GOOGLE_KEYS),
    }


def parse_time(value, key):
    """"08:00" -> (8, 0)."""
    try:
        hour, minute = (int(part) for part in value.split(":"))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return hour, minute
    except ValueError:
        pass
    raise config.ConfigError(f"{key} must be a time like 08:00, not {value!r}")


def get_timezone(name):
    """None (the server's local time) when TIMEZONE is empty."""
    if not name:
        return None
    try:
        return zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        raise config.ConfigError(f"TIMEZONE {name!r} is not a known time zone (like Europe/Madrid)") from None


def build(cfg, tg=None, store=None):
    """Turns the config into (scheduler, bot), with only the features that are fully set up."""
    t = messages.Messages(cfg.get_str("LANGUAGE", "en"))
    tz = get_timezone(cfg.get_str("TIMEZONE"))
    chat_id = cfg.need("TELEGRAM_CHAT_ID")
    if tg is None:
        tg = telegram.Telegram(cfg.need("TELEGRAM_BOT_TOKEN"))
    missing = missing_settings(cfg)
    on = {name for name, keys in missing.items() if not keys}

    def now():
        return datetime.now(tz) if tz else datetime.now().astimezone()

    def send(text):
        tg.send_long(chat_id, text)

    google_api = ai = sheets = None
    if all(cfg.get_str(key) for key in GOOGLE_KEYS):
        google_api = google.Google(*(cfg.get_str(key) for key in GOOGLE_KEYS))
    if cfg.get_str("GEMINI_API_KEY"):
        ai = gemini.Gemini(cfg.get_str("GEMINI_API_KEY"), cfg.get_str("GEMINI_MODEL", "gemini-flash-latest"))
    if "expenses" in on or "reading" in on:
        sheets = google.Sheets(google_api, cfg.get_str("SPREADSHEET_ID"))

    sched = scheduler.Scheduler(
        tz,
        on_failure=lambda name, error: send(t("job_failed", job=t("job_" + name), error=error)),
        on_recovery=lambda name: send(t("job_recovered", job=t("job_" + name))),
    )
    daily = []

    def add_daily(name, key, job):
        value = cfg.get_str(key)
        sched.add(name, scheduler.daily_at(*parse_time(value, key)), lambda: send(job()))
        daily.append((name, value))

    if "calendar" in on:
        calendar_id = cfg.get_str("CALENDAR_ID", "primary")
        work_start = parse_time(cfg.get_str("CALENDAR_WORK_START", "09:00"), "CALENDAR_WORK_START")
        work_end = parse_time(cfg.get_str("CALENDAR_WORK_END", "19:00"), "CALENDAR_WORK_END")
        add_daily("calendar", "CALENDAR_DIGEST_TIME",
                  lambda: digests.calendar_digest(google_api, t, calendar_id, now(), work_start, work_end))
    if "email" in on:
        query = cfg.get_str("EMAIL_QUERY", DEFAULT_EMAIL_QUERY)
        limit = cfg.get_int("EMAIL_MAX_MESSAGES", 25)
        add_daily("email", "EMAIL_DIGEST_TIME", lambda: digests.email_digest(google_api, ai, t, query, limit))
    if "news" in on:
        feeds = cfg.get_list("RSS_FEEDS")
        add_daily("news", "NEWS_DIGEST_TIME", lambda: digests.news_digest(feeds, ai, t, now()))

    expenses = reading = None
    if "expenses" in on:
        expenses = Expenses(sheets, cfg.get_str("EXPENSES_SHEET"), t, now, cfg.get_str("EXPENSE_CURRENCY", "€"))
    if "reading" in on:
        reading = ReadItLater(sheets, cfg.get_str("READING_SHEET"), ai, t, now)

    times = dict(daily)
    for name, label in FEATURES.items():
        if name not in on:
            log.info("%s: off (not set: %s)", label, ", ".join(missing[name]))
        elif name in times:
            log.info("%s: on, every day at %s", label, times[name])
        else:
            log.info("%s: on", label)
    if not on:
        log.warning("No feature is set up: fill in the config file (see the README)")

    return sched, Bot(tg, chat_id, t, expenses, reading, daily, store)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Usage: assistant.py /etc/personal-assistant/personal-assistant.env", file=sys.stderr)
        return 2
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        cfg = config.load(argv[0])
        state_dir = os.environ.get("STATE_DIRECTORY", "/var/lib/personal-assistant")
        sched, bot = build(cfg, store=state.State(os.path.join(state_dir, "state.json")))
    except (OSError, config.ConfigError) as e:
        log.error("%s", e)
        return 1

    stop = threading.Event()
    threading.Thread(target=sched.loop, args=(stop,), name="scheduler", daemon=True).start()
    try:
        bot.poll(stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
