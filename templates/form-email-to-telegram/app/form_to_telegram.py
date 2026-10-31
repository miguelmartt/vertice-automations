"""Contact form (email) → Telegram.

Every CHECK_EVERY_SECONDS it looks for unread emails whose subject contains SUBJECT_KEYWORD, sends a
summary of each one that comes from the website (FORM_FROM, with its DKIM signature) to Telegram and
marks it as read. If the mailbox cannot be read for FAILURES_BEFORE_ALERT checks in a row, it says so
on Telegram (once), and again when it works. If Telegram is what fails, the email waits for the next check.

systemd starts it as the form-to-telegram user:
    python3 form_to_telegram.py /etc/form-to-telegram/form-to-telegram.env
"""

import logging
import signal
import sys
import threading

import config
import messages
from inbox import ForwardError, Inbox, describe
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
            self.inbox.check(self.send)
        except ForwardError as e:
            # The mailbox was read: only Telegram failed, so this is not a "mailbox down".
            log.warning("Could not forward a form email to Telegram; trying again on the next check: %s", e)
        except Exception as e:
            self.failures += 1
            log.warning("Could not read the mailbox (%d in a row): %s", self.failures, describe(e))
            if self.failures == self.failures_before_alert:
                self.notify(t("mailbox_down", user=self.inbox.user, error=describe(e)))
            return
        if self.failures >= self.failures_before_alert:
            self.notify(t("mailbox_back", user=self.inbox.user))
        self.failures = 0

    def send(self, text):
        # No link previews: Telegram would fetch any link someone typed into the form.
        self.tg.send(self.chat_id, text, link_preview_options={"is_disabled": True})

    def notify(self, text):
        try:
            self.send(text)
        except Exception as e:
            log.warning("Could not send the mailbox status to Telegram either: %s", describe(e))

    def loop(self, stop):
        while not stop.is_set():
            self.check_once()
            stop.wait(self.every)


def senders(cfg):
    """(FORM_FROM, DKIM_DOMAIN) as the inbox wants them: "" switches a check off."""
    sender = cfg.get_str("FORM_FROM")
    if not sender:
        raise config.ConfigError("FORM_FROM is not set: the address your website sends the form emails from "
                                 "(or any, to forward them from any sender)")
    if sender.lower() == "any":
        sender = ""
    elif "@" not in sender:
        raise config.ConfigError(f"FORM_FROM must be an email address or any, not {sender!r}")
    dkim = cfg.get_str("DKIM_DOMAIN")
    if dkim.lower() == "off":
        dkim = ""
    elif not dkim:
        dkim = sender.rpartition("@")[2]
    return sender, dkim


def build(cfg):
    messages.set_language(cfg.get_str("LANGUAGE", "en"))
    sender, dkim = senders(cfg)
    inbox = Inbox(
        cfg.need("IMAP_HOST"), cfg.get_int("IMAP_PORT", 993), cfg.need("IMAP_USER"), cfg.need("IMAP_PASSWORD"),
        folder=cfg.get_str("IMAP_FOLDER", "INBOX"), subject=cfg.get_str("SUBJECT_KEYWORD"),
        fields=cfg.get_list("FIELDS"), message_start=cfg.get_str("MESSAGE_START"),
        message_end=cfg.get_str("MESSAGE_END"), site=cfg.get_str("SITE_NAME"), sender=sender, dkim_domain=dkim,
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
    log.info("Watching %s for form emails (sender: %s, DKIM: %s)", watcher.inbox.user,
             watcher.inbox.sender or "any", watcher.inbox.dkim_domain or "off")
    watcher.loop(stop)
    log.info("Stopped")


if __name__ == "__main__":
    main()
