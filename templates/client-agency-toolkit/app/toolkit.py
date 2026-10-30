"""Agency toolkit: watches client sites (Telegram alerts) and emails a weekly analytics report.

Usage: python3 toolkit.py /etc/agency-toolkit/agency-toolkit.env

The invoice generator is a command of its own (invoice.py); this service only says whether it is set up.
Each feature stays off until its settings are filled in.
"""

import logging
import os
import signal
import sys
import threading
from datetime import datetime

import config
import invoice
import mailer
import messages
import report
import scheduler
import uptime
from state import State
from telegram import Telegram

log = logging.getLogger("toolkit")

DEFAULT_STATE_DIR = "/var/lib/agency-toolkit"


def telegram_missing(settings):
    return [key for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not settings.get_str(key)]


def features(settings):
    """What each feature still needs, {feature: [missing settings]}. An empty list means it is on."""
    return {
        "uptime": uptime.missing_settings(settings) + telegram_missing(settings),
        "report": report.missing_settings(settings) + mailer.missing_settings(settings),
        "invoices": invoice.missing_settings(settings) + mailer.missing_settings(settings),
    }


def build(settings, state, telegram=None):
    """The scheduler with the jobs that are on. Raises ConfigError if a setting is wrong."""
    texts = messages.load(settings.get_str("LANGUAGE", "en"))
    tz = report.zone(settings)
    chat_id = settings.get_str("TELEGRAM_CHAT_ID")
    if telegram is None and not telegram_missing(settings):
        telegram = Telegram(settings.get_str("TELEGRAM_BOT_TOKEN"))

    def say(text):
        telegram.send(chat_id, text, link_preview_options={"is_disabled": True})

    def on_failure(name, error):
        say(texts["job_failed"].format(job=texts["job_" + name], error=str(error)[:500]))

    def on_recovery(name):
        say(texts["job_recovered"].format(job=texts["job_" + name]))

    alerts = telegram is not None and bool(chat_id)
    jobs = scheduler.Scheduler(tz, on_failure if alerts else None, on_recovery if alerts else None)
    missing = features(settings)

    if missing["uptime"]:
        log.info("Uptime monitor: off (set %s)", ", ".join(missing["uptime"]))
    else:
        sites = uptime.parse_sites(settings)
        minutes = settings.get_int("UPTIME_INTERVAL_MINUTES", 5)
        timeout = settings.get_int("UPTIME_TIMEOUT_SECONDS", 10)
        if minutes < 1 or timeout < 1:
            raise config.ConfigError("UPTIME_INTERVAL_MINUTES and UPTIME_TIMEOUT_SECONDS must be 1 or more")
        monitor = uptime.Monitor(sites, say, state, texts, timeout=timeout)
        jobs.add("uptime", scheduler.every(minutes * 60), monitor.run)
        log.info("Uptime monitor: on (%d site(s), every %d min)", len(sites), minutes)

    if missing["report"]:
        log.info("Weekly report: off (set %s)", ", ".join(missing["report"]))
    else:
        weekday, hour, minute = report.schedule(settings)
        # A wrong REPORT_DAYS fails now rather than on the first report.
        report.period(datetime.now(tz).date(), settings.get_int("REPORT_DAYS", 7))

        def send_report():
            report.send(settings, texts, datetime.now(tz))

        jobs.add("report", scheduler.daily_at(hour, minute, weekday), send_report)
        log.info(
            "Weekly report: on (%s, %s at %02d:%02d, to %s)", report.provider(settings),
            report.DAYS[weekday], hour, minute, ", ".join(settings.get_list("REPORT_TO")),
        )

    if missing["invoices"]:
        log.info("Invoices (invoice.py): off (set %s)", ", ".join(missing["invoices"]))
    else:
        log.info("Invoices (invoice.py): ready")

    if not alerts:
        log.info("Telegram: off, job failures are only logged (set %s)", ", ".join(telegram_missing(settings)))
    if not jobs.jobs:
        log.warning("No scheduled feature is on: fill in the config file and restart the service")
    return jobs


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: toolkit.py /etc/agency-toolkit/agency-toolkit.env", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    state_dir = os.environ.get("STATE_DIRECTORY", DEFAULT_STATE_DIR)
    try:
        jobs = build(config.load(args[0]), State(os.path.join(state_dir, "state.json")))
    except (OSError, config.ConfigError) as e:
        log.error("%s", e)
        return 1

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    jobs.loop(stop)
    log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
