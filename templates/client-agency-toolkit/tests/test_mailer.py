import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import mailer  # noqa: E402
from config import Config, ConfigError  # noqa: E402

SETTINGS = Config(
    SMTP_HOST="smtp.example.com",
    SMTP_USER="user@example.com",
    SMTP_PASSWORD="TEST_PASSWORD",
    SMTP_FROM="Your Company <reports@example.com>",
)


class FakeSMTP:
    """Stands in for smtplib.SMTP and smtplib.SMTP_SSL, and remembers what happened."""

    last = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.context = host, port, context
        self.tls = False
        self.logins = []
        self.sent = []
        FakeSMTP.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.tls = True

    def login(self, user, password):
        self.logins.append((user, password))

    def send_message(self, msg):
        self.sent.append(msg)


class MailerTest(unittest.TestCase):
    def send(self, settings, **kwargs):
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch("smtplib.SMTP_SSL", FakeSMTP) as ssl_class:
            mailer.send(settings, ["client@example.com"], "Subject", "Plain text", **kwargs)
        return FakeSMTP.last, ssl_class

    def test_starttls_by_default(self):
        smtp, _ = self.send(SETTINGS, html="<p>Hello</p>")
        self.assertEqual((smtp.host, smtp.port, smtp.tls), ("smtp.example.com", 587, True))
        self.assertEqual(smtp.logins, [("user@example.com", "TEST_PASSWORD")])
        (msg,) = smtp.sent
        self.assertEqual(msg["To"], "client@example.com")
        self.assertEqual(msg["From"], "Your Company <reports@example.com>")
        self.assertTrue(msg["Message-ID"].endswith("@example.com>"))
        self.assertEqual(msg.get_content_type(), "multipart/alternative")
        self.assertEqual(msg.get_body(("html",)).get_content().strip(), "<p>Hello</p>")
        self.assertEqual(msg.get_body(("plain",)).get_content().strip(), "Plain text")

    def test_ssl(self):
        smtp, _ = self.send(Config(SETTINGS, SMTP_SECURITY="ssl"))
        self.assertEqual(smtp.port, 465)
        self.assertFalse(smtp.tls)
        self.assertIsNotNone(smtp.context)

    def test_plain_relay_without_login(self):
        smtp, _ = self.send(Config(SMTP_HOST="localhost", SMTP_FROM="reports@example.com", SMTP_SECURITY="none"))
        self.assertEqual((smtp.port, smtp.tls, smtp.logins), (25, False, []))

    def test_custom_port(self):
        smtp, _ = self.send(Config(SETTINGS, SMTP_PORT="2525"))
        self.assertEqual(smtp.port, 2525)

    def test_attachment(self):
        smtp, _ = self.send(SETTINGS, attachments=[("invoice-1.pdf", b"%PDF-1.7", "application/pdf")])
        (attachment,) = list(smtp.sent[0].iter_attachments())
        self.assertEqual(attachment.get_filename(), "invoice-1.pdf")
        self.assertEqual(attachment.get_content(), b"%PDF-1.7")

    def test_bad_security(self):
        with self.assertRaises(ConfigError):
            self.send(Config(SETTINGS, SMTP_SECURITY="tls1"))

    def test_missing_settings(self):
        self.assertEqual(mailer.missing_settings(Config()), ["SMTP_HOST", "SMTP_FROM"])
        self.assertEqual(mailer.missing_settings(SETTINGS), [])


if __name__ == "__main__":
    unittest.main()
