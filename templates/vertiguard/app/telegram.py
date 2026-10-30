"""Minimal Telegram Bot API client using only the standard library.

Shared module: every template ships an identical copy, so each one stays self-contained.
"""

import html
import json
import logging
import re
import urllib.error
import urllib.request

log = logging.getLogger("telegram")

MAX_TEXT = 4096


class TelegramError(Exception):
    pass


class Telegram:
    def __init__(self, token):
        self._url = f"https://api.telegram.org/bot{token}/"

    def call(self, method, params=None, timeout=30):
        req = urllib.request.Request(
            self._url + method,
            data=json.dumps(params or {}).encode(),
            headers={"Content-Type": "application/json"},
        )
        # Errors never include the URL: the token is inside it.
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["result"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            e.close()
            raise TelegramError(f"{method}: HTTP {e.code} {detail}") from None
        except OSError as e:
            raise TelegramError(f"{method}: {getattr(e, 'reason', e)}") from None

    def send(self, chat_id, text, markdown=False, html=False, **extra):
        """Sends a message. If Telegram rejects the Markdown or HTML, it is sent again as plain text."""
        params = {"chat_id": chat_id, "text": text[:MAX_TEXT], **extra}
        mode = "HTML" if html else "Markdown" if markdown else None
        if mode:
            try:
                return self.call("sendMessage", {**params, "parse_mode": mode})
            except TelegramError as e:
                if "can't parse entities" not in str(e):
                    raise
                log.warning("Telegram rejected the %s; sending as plain text", mode)
                if html:
                    params["text"] = plain(text)[:MAX_TEXT]
        return self.call("sendMessage", params)

    def edit(self, chat_id, message_id, text, html=False, **extra):
        """Replaces the text (and buttons) of a message. Editing it to the same content is not an error."""
        params = {"chat_id": chat_id, "message_id": message_id, "text": text[:MAX_TEXT], **extra}
        if html:
            params["parse_mode"] = "HTML"
        try:
            return self.call("editMessageText", params)
        except TelegramError as e:
            if "message is not modified" in str(e):
                return None
            raise

    def send_long(self, chat_id, text, **extra):
        """Plain text of any length, split into several messages if needed."""
        for i in range(0, max(len(text), 1), MAX_TEXT):
            self.send(chat_id, text[i:i + MAX_TEXT], **extra)

    def updates(self, offset, timeout=50, allowed=("message", "callback_query")):
        """Long polling. Removes a webhook left by another tool (n8n, for example) if there is one."""
        params = {"offset": offset, "timeout": timeout, "allowed_updates": list(allowed)}
        try:
            return self.call("getUpdates", params, timeout=timeout + 20)
        except TelegramError as e:
            if "webhook is active" not in str(e):
                raise
            log.info("The bot had a webhook set; removing it to use long polling")
            self.call("deleteWebhook")
            return []


def md(value):
    """Escapes a value for Telegram's Markdown (the underscores of a file name, for example)."""
    text = str(value)
    for c in "_*`[":
        text = text.replace(c, "\\" + c)
    return text


def plain(text):
    """HTML message → plain text, for when Telegram rejects the markup."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))
