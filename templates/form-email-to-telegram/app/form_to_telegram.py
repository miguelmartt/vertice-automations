"""Contact form (email) → Telegram.

Every CHECK_EVERY_SECONDS it looks for unread emails whose subject contains SUBJECT_KEYWORD, sends a
summary of each one to Telegram and marks it as read. If the mailbox cannot be read for
FAILURES_BEFORE_ALERT checks in a row, it says so on Telegram (once), and again when it works.

systemd starts it as the form-to-telegram user:
    python3 form_to_telegram.py /etc/form-to-telegram/form-to-telegram.env
"""

import logging
import signal
import sys
import threading

import config
import messages
from inbox import Inbox
from messages import t
from telegram import Telegram

log = logging.getLogger("form-to-telegram")
DEFAULT_CONFIG = "/etc/form-to-telegram/form-to-telegram.env"


class Watcher:
    def __init__(self, inbox, telegram, chat_id, every=60, failures_before_alert=5):
        self.inbox = inbox
        self.tg = telegram
        self.chat_id = chat_id
        self.every = every
        self.failures_before_alert = failures_before_alert
        self.failures = 0

    def check_once(self):
        try:
            self.inbox.check(lambda text: self.tg.send(self.chat_id, text))
        except Exception as e:
            self.failures += 1
            log.warning("Could not read the mailbox (%d in a row): %s", self.failures, e)
            if self.failures == self.failures_before_alert:
                self.notify(t("mailbox_down", user=self.inbox.user, error=str(e)[:300]))
            return
        if self.failures >= self.failures_before_alert:
            self.notify(t("mailbox_back", user=self.inbox.user))
        self.failures = 0

    def notify(self, text):
        try:
            self.tg.send(self.chat_id, text)
        except Exception:
            log.exception("Could not send the mailbox status to Telegram either")

    def loop(self, stop):
        while not stop.is_set():
            self.check_once()
            stop.wait(self.every)


def build(cfg):
    messages.set_language(cfg.get_str("LANGUAGE", "en"))
    inbox = Inbox(
        cfg.need("IMAP_HOST"), cfg.get_int("IMAP_PORT", 993), cfg.need("IMAP_USER"), cfg.need("IMAP_PASSWORD"),
        folder=cfg.get_str("IMAP_FOLDER", "INBOX"), subject=cfg.get_str("SUBJECT_KEYWORD"),
        fields=cfg.get_list("FIELDS"), message_start=cfg.get_str("MESSAGE_START"),
        message_end=cfg.get_str("MESSAGE_END"), site=cfg.get_str("SITE_NAME"),
    )
    return Watcher(inbox, Telegram(cfg.need("BOT_TOKEN")), int(cfg.need("TELEGRAM_CHAT_ID")),
                   every=cfg.get_int("CHECK_EVERY_SECONDS", 60),
                   failures_before_alert=cfg.get_int("FAILURES_BEFORE_ALERT", 5))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    watcher = build(config.load(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    log.info("Watching %s for form emails", watcher.inbox.user)
    watcher.loop(stop)
    log.info("Stopped")


if __name__ == "__main__":
    main()
