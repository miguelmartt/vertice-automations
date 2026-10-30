"""The Telegram bot: long polling, only for TELEGRAM_CHAT_ID, one bot for the expense logger and read-it-later.

How a message is routed:
  /month or /mes      -> this month's expenses by category
  any other /command  -> help
  contains a link     -> read-it-later (the first http(s) link)
  anything else       -> an expense ("12 lunch"); if it has no amount, a hint
"""

import logging
import re

import telegram

log = logging.getLogger("bot")

URL = re.compile(r"https?://\S+", re.IGNORECASE)
MONTH_COMMANDS = ("month", "mes")


def clean_url(url):
    """Drops punctuation stuck to the end of a link: "(see https://example.com/a)." -> https://example.com/a"""
    url = url.rstrip(".,;:!?'\"»>")
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1].rstrip(".,;:!?'\"»>")
    return url


def find_url(message):
    """The first http(s) link of a message: written in the text or caption, or hidden behind linked text."""
    for key in ("text", "caption"):
        match = URL.search(message.get(key) or "")
        if match:
            return clean_url(match.group(0))
    for entity in (message.get("entities") or []) + (message.get("caption_entities") or []):
        url = entity.get("url") or ""
        if entity.get("type") == "text_link" and URL.match(url):
            return url
    return None


def route(text, url=None):
    """What a message is for: "month", "help", "link" or "expense"."""
    if text.startswith("/"):
        command = text.split()[0][1:].split("@")[0].lower()  # /mes@my_bot -> mes
        return "month" if command in MONTH_COMMANDS else "help"
    if url:
        return "link"
    return "expense" if text else "help"


class Bot:
    """expenses and reading are None when those features are off. daily is [(job name, "HH:MM")] for /help."""

    def __init__(self, tg, chat_id, t, expenses=None, reading=None, daily=(), store=None):
        self.telegram = tg
        self.chat_id = str(chat_id)
        self.t = t
        self.expenses = expenses
        self.reading = reading
        self.daily = list(daily)
        self.store = store

    def poll(self, stop):
        """Answers messages until stop is set. The offset is saved, so a restart does not handle a
        message twice (and does not log the same expense twice)."""
        offset = self.store.get("telegram_offset", 0) if self.store is not None else 0
        while not stop.is_set():
            try:
                updates = self.telegram.updates(offset, allowed=("message",))
            except telegram.TelegramError as e:
                log.warning("Could not get the messages: %s", e)
                stop.wait(15)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                if self.store is not None:
                    self.store.set("telegram_offset", offset)
                if "message" in update:
                    self.handle(update["message"])

    def handle(self, message):
        if str((message.get("chat") or {}).get("id")) != self.chat_id:
            log.info("Ignoring a message from another chat")
            return
        try:
            reply = self.reply(message)
        except Exception as e:  # one bad message must not stop the bot
            log.exception("Could not handle a message")
            reply = self.t("error", error=e)
        try:
            self.telegram.send_long(self.chat_id, reply)
        except telegram.TelegramError as e:
            log.warning("Could not reply: %s", e)

    def reply(self, message):
        text = (message.get("text") or message.get("caption") or "").strip()
        url = find_url(message)
        kind = route(text, url)
        if kind == "help":
            return self.help()
        if kind == "month":
            return self.expenses.month() if self.expenses else self.t("off_expenses")
        if kind == "link":
            if not self.reading:
                return self.t("off_reading")
            self._typing()
            return self.reading.save(url)
        if self.expenses:
            saved = self.expenses.log(text)
            if saved:
                return saved
            hint = "\n" + self.t("link_hint") if self.reading else ""
            return self.t("expense_unreadable") + hint
        return self.t("reading_send_link") if self.reading else self.help()

    def help(self):
        lines = []
        if self.expenses:
            lines.append(self.t("help_expenses"))
        if self.reading:
            lines.append(self.t("help_reading"))
        if self.daily:
            items = ", ".join(self.t("help_" + name, time=at) for name, at in self.daily)
            lines.append(self.t("help_daily", items=items))
        if not lines:
            return self.t("help_nothing")
        return self.t("help_title") + "\n\n" + "\n".join(lines)

    def _typing(self):
        """Shows "typing..." while a link is fetched and summarized; it is only a courtesy."""
        try:
            self.telegram.call("sendChatAction", {"chat_id": self.chat_id, "action": "typing"})
        except telegram.TelegramError:
            pass
