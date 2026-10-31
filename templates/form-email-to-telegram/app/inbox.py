"""Reads the form emails from the mailbox and turns each one into a Telegram message.

Every email is handled on its own, so a broken one never holds up the rest:
- one that does not come from the website (FORM_FROM and its DKIM signature) is not forwarded;
- one that is too big or can't be read gets a short notice with its subject instead;
- those get the $FormFailed keyword, so they are not fetched again and stay unread for you.
The forwarded ones are marked as read. At most MAX_PER_CHECK emails are handled per check.
"""

import email
import email.utils
import html
import imaplib
import logging
import re
import ssl
from email import policy

from messages import t

log = logging.getLogger("inbox")
FAILED = "$FormFailed"  # IMAP keyword on the emails that were not forwarded
MAX_PER_CHECK = 10
MAX_SIZE = 5 * 1024 * 1024  # bigger emails are not downloaded
MAX_HEADER = 65536  # bytes of the From, Subject and Authentication-Results headers that are read
MAX_TEXT = 65536  # characters of the body that are looked at
MAX_FALLBACK_BODY = 1500
MAX_SUBJECT = 100
HEADERS = f"(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT AUTHENTICATION-RESULTS)]<0.{MAX_HEADER}>)"

# Linear-time patterns only: an email is untrusted text.
TAG = re.compile(r"<[^<>]*>")
BLOCK_START = re.compile(r"<(style|script|head)\b", re.I)
BLOCK_END = {name: re.compile(r"</" + name + r"\s*>", re.I) for name in ("style", "script", "head")}
COMMENT = re.compile(r"\([^()]*\)")
DKIM_PASS = re.compile(r"\s*dkim\s*=\s*pass\b")
SIGNER = re.compile(r"\bheader\.(?:d\s*=\s*|i\s*=\s*[^\s;@]*@)\"?([a-z0-9.-]+)")
SIZE = re.compile(rb"RFC822\.SIZE ([0-9]{1,15})")


class ForwardError(Exception):
    """Telegram did not take a message. The email is left as it was, for the next check."""


class Inbox:
    def __init__(self, host, port, user, password, folder="INBOX", subject="", fields=(),
                 message_start="", message_end="", site="", sender="", dkim_domain=""):
        self.host, self.port, self.user, self.password, self.folder = host, port, user, password, folder
        self.subject = subject
        self.fields = list(fields)
        self.message_start = message_start
        self.message_end = message_end
        self.site = site
        self.sender = sender.lower()  # empty = any sender
        self.dkim_domain = dkim_domain.lower()  # empty = no DKIM check

    def check(self, send):
        """Sends every new form email to send(text). Returns how many it forwarded.

        A mailbox that can't be read raises its IMAP or network error; ForwardError means it was read
        but Telegram did not take a message.
        """
        # A verified certificate: imaplib's default context does not check it, and this login carries a password.
        imap = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ssl.create_default_context(), timeout=30)
        forwarded = rejected = 0
        try:
            imap.login(self.user, self.password)
            imap.select(self.folder)
            criteria = ["UNSEEN", "UNKEYWORD", FAILED]
            if self.subject:
                criteria += ["SUBJECT", '"' + self.subject.replace('"', "").replace("\\", "") + '"']
            _, ids = imap.search(None, *criteria)
            for num in ids[0].split()[:MAX_PER_CHECK]:
                try:
                    outcome = self.handle(imap, num, send)
                except imaplib.IMAP4.abort:  # the connection is gone: the mailbox is down
                    raise
                except imaplib.IMAP4.error as e:  # the server would not hand over this email only
                    log.warning("Could not fetch an email: %s", describe(e))
                    outcome = self.notice(imap, num, send, t("failed", subject="?"))
                forwarded += outcome == "forwarded"
                rejected += outcome == "rejected"
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        if rejected:
            try:
                send(t("not_from_site", n=rejected))
            except Exception as e:
                log.warning("Could not say on Telegram that %d emails were not forwarded: %s", rejected, describe(e))
        return forwarded

    def handle(self, imap, num, send):
        """One email: "forwarded", "noticed" (too big or unreadable), "rejected" (not from the website) or "skipped"."""
        head, size = fetch(imap, num, HEADERS)
        try:
            headers = email.message_from_bytes(head, policy=policy.default)
            subject = str(headers.get("subject", ""))
            reason = self.not_from_site(headers)
        except Exception as e:  # the parser can raise RecursionError, IndexError, AttributeError…
            log.warning("Could not read the headers of an email: %s", describe(e))
            subject, reason = "", "unreadable headers" if (self.sender or self.dkim_domain) else ""
        # Safety net: some servers match SUBJECT loosely, so check the decoded subject again.
        if subject and self.subject and self.subject.lower() not in subject.lower():
            self.flag(imap, num)
            return "skipped"
        if reason:
            log.info("Not forwarded: an email with the form subject failed the %s check", reason)
            self.flag(imap, num)
            return "rejected"
        if size is None or size > MAX_SIZE:  # every IMAP server gives the size; without it, don't risk it
            log.info("Not forwarded: a form email of %s bytes", size)
            mb = f"{size / 1048576:.1f}" if size is not None else "?"
            return self.notice(imap, num, send, t("too_big", size=mb, subject=short(subject)))

        raw, _ = fetch(imap, num, "(BODY.PEEK[])")
        try:
            text = self.summary(email.message_from_bytes(raw, policy=policy.default))
        except Exception as e:  # RecursionError, IndexError, AttributeError, LookupError… from the parser
            log.warning("Could not read a form email: %s", describe(e))
            return self.notice(imap, num, send, t("failed", subject=short(subject)))
        try:
            send(text)
        except Exception as e:
            log.warning("Telegram did not take a form email: %s", describe(e))
            return self.notice(imap, num, send, t("failed", subject=short(subject)))
        if not store(imap, num, "\\Seen"):
            log.warning("Could not mark a forwarded email as read; it may come again")
        log.info("Form email forwarded")
        return "forwarded"

    def notice(self, imap, num, send, text):
        """Sends a short notice instead of the email and flags it, so it is not fetched again."""
        try:
            send(text)
        except Exception as e:
            raise ForwardError(describe(e)) from None
        self.flag(imap, num)
        return "noticed"

    def flag(self, imap, num):
        """Adds the $FormFailed keyword, so the search skips the email and it stays unread. A server
        that does not take keywords gets it marked as read instead, which also keeps it out of the search."""
        if not (store(imap, num, FAILED) or store(imap, num, "\\Seen")):
            log.warning("Could not flag an email that was not forwarded; it will be looked at again")

    def not_from_site(self, headers):
        """Why the email does not pass for one from the website ("" if it does)."""
        if self.sender:
            senders = headers.get_all("from") or []
            addresses = email.utils.getaddresses([str(h) for h in senders])
            if len(addresses) != 1 or addresses[0][1].lower() != self.sender:
                return "sender"
        if self.dkim_domain and not dkim_pass(headers, self.dkim_domain):
            return "DKIM"
        return ""

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


def store(imap, num, flag):
    """Adds a flag to an email. False if the server refused it; a lost connection still raises."""
    try:
        return imap.store(num, "+FLAGS", flag)[0] == "OK"
    except imaplib.IMAP4.abort:
        raise
    except imaplib.IMAP4.error:
        return False


def fetch(imap, num, what):
    """(content, RFC822.SIZE) of one email, whatever order the server put them in."""
    typ, data = imap.fetch(num, what)
    if typ != "OK":
        raise imaplib.IMAP4.error(f"FETCH answered {typ}")
    content, rest = b"", b""
    for item in data or []:
        if isinstance(item, tuple):
            rest += item[0]
            content = content or item[1]
        elif isinstance(item, bytes):
            rest += item
    size = SIZE.search(rest)
    return content, int(size.group(1)) if size else None


def dkim_pass(headers, domain):
    """True if the first Authentication-Results header says the DKIM signature of `domain` passed.

    Only the first one counts: the mailbox server adds its own on top, and any further down came
    with the email, so the sender could have written them.
    """
    results = headers.get_all("authentication-results") or []
    if not results:
        return False
    text = COMMENT.sub("", str(results[0])[:4096].lower())
    for result in text.split(";")[1:]:  # the part before the first ";" is the server's name
        if DKIM_PASS.match(result) and any(m.group(1) == domain for m in SIGNER.finditer(result)):
            return True
    return False


def body_text(msg):
    part = msg.get_body(preferencelist=("plain",))
    if part is not None:
        return decoded(part)[:MAX_TEXT]
    part = msg.get_body(preferencelist=("html",))
    return html_to_text(decoded(part)) if part is not None else ""


def decoded(part):
    """The text of a part. A charset Python doesn't know (or an empty one) falls back to UTF-8."""
    payload = (part.get_payload(decode=True) or b"")[:MAX_TEXT * 4]
    try:
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except (LookupError, ValueError):
        return payload.decode("utf-8", errors="replace")


def html_to_text(content):
    """HTML → text in one forward pass: drops the style, script and head blocks, then the tags."""
    content = content[:MAX_TEXT]
    kept, pos = [], 0
    while True:
        start = BLOCK_START.search(content, pos)
        if not start:
            kept.append(content[pos:])
            break
        kept.append(content[pos:start.start()] + " ")
        end = BLOCK_END[start.group(1).lower()].search(content, start.end())
        if not end:
            break  # a block that is never closed runs to the end
        pos = end.end()
    return html.unescape(TAG.sub("\n", "".join(kept)))


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


def short(text):
    """A subject for a notice: one line, without control characters, at most MAX_SUBJECT characters."""
    text = " ".join("".join(c if c.isprintable() else " " for c in text[:MAX_SUBJECT * 2]).split())
    return (text[:MAX_SUBJECT] + "…" if len(text) > MAX_SUBJECT else text) or "?"


def describe(error):
    """An error for the log: its type and a short repr, so text from an email can't add lines to it."""
    return f"{type(error).__name__}: {str(error)!r:.200}"
