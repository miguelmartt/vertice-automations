"""Reads the form emails from the mailbox and turns each one into a Telegram message."""

import email
import html
import imaplib
import logging
import re
from email import policy

from messages import t

log = logging.getLogger("inbox")
MAX_FALLBACK_BODY = 1500


class Inbox:
    def __init__(self, host, port, user, password, folder="INBOX", subject="", fields=(),
                 message_start="", message_end="", site=""):
        self.host, self.port, self.user, self.password, self.folder = host, port, user, password, folder
        self.subject = subject
        self.fields = list(fields)
        self.message_start = message_start
        self.message_end = message_end
        self.site = site

    def check(self, send):
        """Sends every unread form email to send(text) and marks it as read. Returns how many it sent."""
        imap = imaplib.IMAP4_SSL(self.host, self.port, timeout=30)
        sent = 0
        try:
            imap.login(self.user, self.password)
            imap.select(self.folder)
            criteria = ["UNSEEN"] + (["SUBJECT", '"' + self.subject.replace('"', "") + '"'] if self.subject else [])
            _, ids = imap.search(None, *criteria)
            for num in ids[0].split():
                _, data = imap.fetch(num, "(BODY.PEEK[])")
                msg = email.message_from_bytes(data[0][1], policy=policy.default)
                # Safety net: some servers match SUBJECT loosely, so check the decoded subject again.
                if self.subject and self.subject.lower() not in str(msg.get("subject", "")).lower():
                    continue
                send(self.summary(msg))
                imap.store(num, "+FLAGS", "\\Seen")
                sent += 1
                log.info("Form email forwarded")
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        return sent

    def summary(self, msg):
        """The configured fields and the message. If none is found, the subject and the body as they are."""
        text = body_text(msg)
        lines = [line.replace("\xa0", " ").strip() for line in text.splitlines()]
        lines = [line for line in lines if line]

        found = [(label, field(lines, label)) for label in self.fields]
        found = [(label, value) for label, value in found if value]
        message = between(lines, self.message_start, self.message_end) if self.message_start else ""

        title = t("title_site", site=self.site) if self.site else t("title")
        if not found and not message:
            subject = str(msg.get("subject", "")).strip()
            return "\n".join([title, "", t("subject", subject=subject), "", text.strip()[:MAX_FALLBACK_BODY]])
        out = [title, ""] + [f"{label}: {value}" for label, value in found]
        if message:
            out += ["", t("message"), message]
        return "\n".join(out)


def body_text(msg):
    part = msg.get_body(preferencelist=("plain",))
    if part is not None:
        return part.get_content()
    part = msg.get_body(preferencelist=("html",))
    return html_to_text(part.get_content()) if part is not None else ""


def html_to_text(content):
    content = re.sub(r"(?is)<(style|script|head)\b.*?</\1>", " ", content)
    return html.unescape(re.sub(r"<[^>]+>", "\n", content))


def field(lines, label):
    """The value after "Label:" on the same line, or on the next line if it is empty."""
    pattern = re.compile("^" + re.escape(label) + r"\s*:?\s*(.*)$", re.I)
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            return m.group(1).strip() or (lines[i + 1] if i + 1 < len(lines) else "")
    return ""


def between(lines, start, end):
    """The lines after the one that starts with `start`, up to the one that starts with `end`."""
    for i, line in enumerate(lines):
        if line.lower().startswith(start.lower()):
            rest = lines[i + 1:]
            stop = next((j for j, other in enumerate(rest) if end and other.lower().startswith(end.lower())), len(rest))
            return "\n".join(rest[:stop])
    return ""
