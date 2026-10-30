"""VertiGuard: watches a VPS and reports on Telegram.

One process, up to three threads:
  alerts       scheduled checks (services, disk/RAM, SSL, backups, fail2ban, updates)
  bot          the DevOps bot with /menu and Gemini (only if DEVOPS_BOT_TOKEN is set)
  uptimerobot  the UptimeRobot webhook (only if WEBHOOK_PORT is set)

systemd starts it as the vertiguard user: python3 vertiguard.py /etc/vertiguard/vertiguard.env
"""

import logging
import os
import signal
import sys
import threading
from zoneinfo import ZoneInfo

import config
import messages
import uptimerobot
from alerts import Alerts
from devops_bot import DevopsBot
from gemini import Gemini
from messages import t
from probes import Probes
from scheduler import Scheduler
from state import State
from telegram import Telegram, md

log = logging.getLogger("vertiguard")
DEFAULT_CONFIG = "/etc/vertiguard/vertiguard.env"


def build(cfg):
    """Turns the config into the threads to run. Separate from main() so it can be tested."""
    messages.set_language(cfg.get_str("LANGUAGE", "en"))
    tz = ZoneInfo(cfg.get_str("TIMEZONE", "UTC"))
    chat_id = int(cfg.need("TELEGRAM_CHAT_ID"))
    alerts_tg = Telegram(cfg.need("ALERTS_BOT_TOKEN"))
    probes = Probes(cfg.get_str("PROBES_DIR", "/opt/vertiguard"))
    state = State(os.path.join(cfg.get_str("STATE_DIR", "/var/lib/vertiguard"), "state.json"))

    alerts = Alerts(alerts_tg, chat_id, state, probes,
                    resource_pct=cfg.get_int("RESOURCE_ALERT_PCT", 80), ssl_days=cfg.get_int("SSL_ALERT_DAYS", 15))
    scheduler = Scheduler(
        tz,
        on_failure=lambda job, e: alerts_tg.send(
            chat_id, t("job_failed", job=t("job_" + job), error=md(str(e)[:300])), markdown=True),
        on_recovery=lambda job: alerts_tg.send(chat_id, t("job_recovered", job=t("job_" + job)), markdown=True),
    )
    for name, when, job in alerts.jobs(cfg.get_int("REPORT_HOUR", 9), cfg.get_int("BACKUP_CHECK_HOUR", 6)):
        scheduler.add(name, when, job)

    parts = {"alerts": (scheduler.loop, True)}
    if cfg.get_str("DEVOPS_BOT_TOKEN"):
        gemini = Gemini(cfg.get_str("GEMINI_API_KEY"), cfg.get_str("GEMINI_MODEL", "gemini-flash-latest")) \
            if cfg.get_str("GEMINI_API_KEY") else None
        bot = DevopsBot(Telegram(cfg.get_str("DEVOPS_BOT_TOKEN")), chat_id, probes, gemini)
        parts["bot"] = (bot.loop, True)
    webhook = None
    if cfg.get_str("WEBHOOK_PORT"):
        webhook = uptimerobot.server(alerts_tg, chat_id, cfg.get_int("WEBHOOK_PORT", 0),
                                     cfg.get_str("WEBHOOK_PATH", "/webhook/uptimerobot"))
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
