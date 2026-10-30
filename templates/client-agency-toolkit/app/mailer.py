"""Sends email over SMTP (STARTTLS, SSL or a plain local relay). Used by the weekly report and the invoices."""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from config import ConfigError

log = logging.getLogger("mailer")

PORTS = {"starttls": 587, "ssl": 465, "none": 25}
TIMEOUT = 30


def missing_settings(settings):
    return [key for key in ("SMTP_HOST", "SMTP_FROM") if not settings.get_str(key)]


def build(sender, to, subject, text, html=None, attachments=()):
    """attachments: (filename, bytes, "type/subtype") tuples."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=parseaddr(sender)[1].rpartition("@")[2] or "localhost")
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for filename, data, mime_type in attachments:
        maintype, _, subtype = mime_type.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def send(settings, to, subject, text, html=None, attachments=()):
    host = settings.need("SMTP_HOST")
    security = settings.get_str("SMTP_SECURITY", "starttls").lower()
    if security not in PORTS:
        raise ConfigError(f"SMTP_SECURITY must be starttls, ssl or none, not {security!r}")
    port = settings.get_int("SMTP_PORT", PORTS[security])
    msg = build(settings.need("SMTP_FROM"), to, subject, text, html, attachments)

    context = ssl.create_default_context()
    if security == "ssl":
        smtp = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=context)
    else:
        smtp = smtplib.SMTP(host, port, timeout=TIMEOUT)
    with smtp:
        if security == "starttls":
            smtp.starttls(context=context)
        user = settings.get_str("SMTP_USER")
        if user:
            smtp.login(user, settings.get_str("SMTP_PASSWORD"))
        smtp.send_message(msg)
    log.info("Email %r sent to %s", subject, ", ".join(to))
