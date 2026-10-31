"""VertiGuard: watches a VPS and reports on Telegram, through one bot.

One process, up to three threads:
  alerts       scheduled checks that alert on changes, and the daily report
  bot          commands, the button panel and questions to Gemini (unless COMMANDS=off)
  uptimerobot  the UptimeRobot webhook (only if WEBHOOK_PORT and WEBHOOK_TOKEN are set)

systemd starts it as the vertiguard user: python3 vertiguard.py /etc/vertiguard/vertiguard.env
"""

import logging
import os
import signal
import socket
import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import config
import messages
import uptimerobot
from alerts import Alerts
from bot import Bot
from fmt import esc
from gemini import Gemini
from messages import t
from panels import Context
from probes import Probes
from scheduler import Scheduler
from snapshot import Snapshot
from state import State
from telegram import Telegram

log = logging.getLogger("vertiguard")
DEFAULT_CONFIG = "/etc/vertiguard/vertiguard.env"


def build(cfg):
    """Turns the config into the threads to run. Separate from main() so it can be tested."""
    messages.set_language(cfg.get_str("LANGUAGE", "en"))
    tz = ZoneInfo(cfg.get_str("TIMEZONE", "UTC"))
    chat_id = int(cfg.need("TELEGRAM_CHAT_ID"))
    token = cfg.get_str("BOT_TOKEN") or cfg.get_str("ALERTS_BOT_TOKEN")  # ALERTS_BOT_TOKEN: the first release's name
    if not token:
        raise config.ConfigError("BOT_TOKEN is not set in the config file")
    tg = Telegram(token)
    probes = Probes(cfg.get_str("PROBES_DIR", "/opt/vertiguard"))
    snapshot = Snapshot(probes)
    state = State(os.path.join(cfg.get_str("STATE_DIR", "/var/lib/vertiguard"), "state.json"))

    server = cfg.get_str("SERVER_NAME") or socket.gethostname().split(".")[0]
    resource_pct = cfg.get_int("RESOURCE_ALERT_PCT", 80)
    ssl_days = cfg.get_int("SSL_ALERT_DAYS", 15)
    backup_hour = cfg.get_int("BACKUP_CHECK_HOUR", 6)
    report = cfg.get_str("REPORT_HOUR", "9")
    report_hour = None if report.lower() == "off" else int(report)
    commands = cfg.get_str("COMMANDS", "on").lower() != "off"

    def context():
        return Context(server, datetime.now(tz), resource_pct, ssl_days, backup_hour)

    alerts = Alerts(tg, chat_id, state, snapshot, context, resource_pct, ssl_days, buttons=commands)
    scheduler = Scheduler(
        tz,
        on_failure=lambda job, e: tg.send(chat_id, t("job_failed", job=t("job_" + job), error=esc(str(e)[:300])), html=True),
        on_recovery=lambda job: tg.send(chat_id, t("job_recovered", job=t("job_" + job)), html=True),
    )
    for name, when, job in alerts.jobs(report_hour, backup_hour):
        scheduler.add(name, when, job)

    parts = {"alerts": (scheduler.loop, True)}
    if commands:
        gemini = Gemini(cfg.get_str("GEMINI_API_KEY"), cfg.get_str("GEMINI_MODEL", "gemini-flash-latest")) \
            if cfg.get_str("GEMINI_API_KEY") else None
        parts["bot"] = (Bot(tg, chat_id, snapshot, probes, context, gemini, report_hour).loop, True)
    webhook = None
    if cfg.get_str("WEBHOOK_PORT"):
        token = cfg.get_str("WEBHOOK_TOKEN")
        if len(token) < uptimerobot.MIN_TOKEN:
            # Without a secret, anyone who finds the URL could send messages to your chat.
            log.error("The UptimeRobot webhook stays off: WEBHOOK_TOKEN is empty or shorter than %d characters "
                      "(make one with: openssl rand -hex 32)", uptimerobot.MIN_TOKEN)
        else:
            webhook = uptimerobot.server(tg, chat_id, cfg.get_int("WEBHOOK_PORT", 0),
                                         cfg.get_str("WEBHOOK_PATH", "/webhook/uptimerobot"), token)
            parts["uptimerobot"] = (webhook.serve_forever, False)
    return parts, webhook


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(threadName)s] %(message)s", stream=sys.stdout)
    parts, webhook = build(config.load(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG))
    stop = threading.Event()
    threads = [threading.Thread(target=run, args=(stop,) if takes_stop else (), name=name, daemon=True)
               for name, (run, takes_stop) in parts.items()]
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    for thread in threads:
        thread.start()
    log.info("VertiGuard running: %s", ", ".join(parts))
    # If a thread dies, exit with an error so systemd restarts the whole service.
    while not stop.wait(30):
        dead = [th.name for th in threads if not th.is_alive()]
        if dead:
            log.error("Threads stopped: %s; exiting so systemd restarts me", ", ".join(dead))
            sys.exit(1)
    if webhook:
        webhook.shutdown()
    log.info("VertiGuard stopped")


if __name__ == "__main__":
    main()
