import string
import unittest
from email.message import EmailMessage
from unittest import mock

import config
import form_to_telegram
import messages
from inbox import Inbox

FORM_EMAIL = """Nuevo contacto desde la web

Empresa: Panadería López
Email:
ana@example.com
Teléfono: 600 000 000
Servicio: Automatización

Mensaje del cliente
Quiero avisos de pedidos.
Gracias.

Responder a: ana@example.com
"""


def make_email(body, subject="📩 Nuevo contacto: Panadería López", html=False):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "web@example.com"
    if html:
        msg.set_content(body, subtype="html")
    else:
        msg.set_content(body)
    return msg


def inbox(**kwargs):
    defaults = dict(host="imap.example.com", port=993, user="contact@example.com", password="x")
    defaults.update(kwargs)
    return Inbox(**defaults)


class SummaryTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("es")

    def tearDown(self):
        messages.set_language("en")

    def test_fields_and_message(self):
        box = inbox(fields=["Empresa", "Email", "Teléfono", "Servicio", "Presupuesto"],
                    message_start="Mensaje del cliente", message_end="Responder a", site="example.com")
        text = box.summary(make_email(FORM_EMAIL))
        self.assertEqual(text.splitlines()[0], "📬 Nuevo contacto de example.com")
        self.assertIn("Empresa: Panadería López", text)
        self.assertIn("Email: ana@example.com", text)  # value on the next line
        self.assertNotIn("Presupuesto", text)  # missing fields are skipped
        self.assertIn("💬 Mensaje:\nQuiero avisos de pedidos.\nGracias.", text)
        self.assertNotIn("Responder a", text)

    def test_fallback_is_subject_and_body(self):
        text = inbox().summary(make_email("Hola, ¿hacéis webs?", subject="Nuevo contacto"))
        self.assertIn("Asunto: Nuevo contacto", text)
        self.assertIn("Hola, ¿hacéis webs?", text)

    def test_html_only_email(self):
        body = "<html><head><style>p{}</style></head><body><p>Empresa: ACME</p></body></html>"
        text = inbox(fields=["Empresa"]).summary(make_email(body, html=True))
        self.assertIn("Empresa: ACME", text)
        self.assertNotIn("p{}", text)


class FakeImap:
    def __init__(self, emails):
        self.emails = emails  # {b"1": EmailMessage}
        self.seen = []
        self.searched = None

    def __call__(self, host, port, timeout):
        return self

    def login(self, user, password):
        pass

    def select(self, folder):
        pass

    def search(self, charset, *criteria):
        self.searched = criteria
        return "OK", [b" ".join(self.emails)]

    def fetch(self, num, what):
        return "OK", [(b"", self.emails[num].as_bytes())]

    def store(self, num, flags, value):
        self.seen.append(num)

    def logout(self):
        pass


class CheckTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_sends_and_marks_as_read(self):
        imap = FakeImap({b"1": make_email("Name: Ana", subject="New contact: Ana"),
                         b"2": make_email("spam", subject="Newsletter")})
        sent = []
        with mock.patch("imaplib.IMAP4_SSL", imap):
            count = inbox(subject="New contact", fields=["Name"]).check(sent.append)
        self.assertEqual(count, 1)
        self.assertEqual(imap.seen, [b"1"])  # the newsletter matched loosely on the server but is skipped
        self.assertIn("Name: Ana", sent[0])
        self.assertEqual(imap.searched, ("UNSEEN", "SUBJECT", '"New contact"'))


class FakeTelegram:
    def __init__(self):
        self.texts = []

    def send(self, chat_id, text, **extra):
        self.texts.append(text)


class BrokenInbox:
    user = "contact@example.com"

    def __init__(self):
        self.broken = True

    def check(self, send):
        if self.broken:
            raise OSError("login failed")
        return 0


class WatcherTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_alerts_once_after_several_failures_and_on_recovery(self):
        box, tg = BrokenInbox(), FakeTelegram()
        watcher = form_to_telegram.Watcher(box, tg, 42, failures_before_alert=3)
        with self.assertLogs("form-to-telegram", level="WARNING"):
            for _ in range(5):
                watcher.check_once()
        self.assertEqual(len(tg.texts), 1)
        self.assertIn("Can't read the mailbox", tg.texts[0])
        box.broken = False
        watcher.check_once()
        watcher.check_once()
        self.assertEqual(len(tg.texts), 2)
        self.assertIn("again", tg.texts[1])

    def test_build_from_config(self):
        cfg = config.Config({"TELEGRAM_CHAT_ID": "42", "BOT_TOKEN": "x", "IMAP_HOST": "imap.example.com",
                             "IMAP_USER": "u", "IMAP_PASSWORD": "p", "FIELDS": "Name, Email", "LANGUAGE": "es"})
        watcher = form_to_telegram.build(cfg)
        self.assertEqual(watcher.inbox.fields, ["Name", "Email"])
        self.assertEqual(watcher.chat_id, 42)
        with self.assertRaises(config.ConfigError):
            form_to_telegram.build(config.Config({"TELEGRAM_CHAT_ID": "42"}))


class MessagesTest(unittest.TestCase):
    def test_same_keys_and_placeholders(self):
        def fields(text):
            return {name for _, name, _, _ in string.Formatter().parse(text) if name}

        for key, text in messages.TEXTS["en"].items():
            self.assertEqual(fields(messages.TEXTS["es"][key]), fields(text), key)
        self.assertEqual(set(messages.TEXTS["es"]), set(messages.TEXTS["en"]))


if __name__ == "__main__":
    unittest.main()
