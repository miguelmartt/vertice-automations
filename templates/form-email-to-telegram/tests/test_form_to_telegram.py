import re
import ssl
import string
import time
import unittest
from email.message import EmailMessage
from unittest import mock

import config
import form_to_telegram
import inbox as inbox_module
import messages
import telegram
from inbox import FAILED, ForwardError, Inbox

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
DKIM_OK = "mx.example.net; dkim=pass (2048-bit key) header.d=example.com header.s=s1 header.b=abc; spf=pass"


def make_email(body, subject="📩 Nuevo contacto: Panadería López", html=False, sender="web@example.com",
               auth=DKIM_OK):
    msg = EmailMessage()
    if auth:
        msg["Authentication-Results"] = auth
    msg["Subject"] = subject
    msg["From"] = sender
    if html:
        msg.set_content(body, subtype="html")
    else:
        msg.set_content(body)
    return msg


def raw_email(content_type, body, subject="New contact: broken"):
    """An email as bytes, with a Content-Type EmailMessage would not let us write."""
    return (f"Authentication-Results: {DKIM_OK}\nFrom: web@example.com\nSubject: {subject}\n"
            f"Content-Type: {content_type}\n\n").encode() + body


def inbox(**kwargs):
    defaults = dict(host="imap.example.com", port=993, user="contact@example.com", password="x",
                    sender="web@example.com", dkim_domain="example.com")
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


class HtmlTest(unittest.TestCase):
    def test_blocks_and_tags_go(self):
        text = inbox_module.html_to_text("<HEAD><title>x</title></head>a<script>1<2</SCRIPT >b<style>c")
        self.assertEqual(text.split(), ["a", "b"])  # an unclosed <style> runs to the end

    def test_linear_time_on_hostile_html(self):
        started = time.monotonic()
        for hostile in ("<style" * 20000, "<" * 200000, "<a " * 70000, "<script>" + "</scrip" * 20000):
            inbox_module.html_to_text(hostile)
        self.assertLess(time.monotonic() - started, 2)


class FakeImap:
    """A mailbox in memory: {b"1": EmailMessage or bytes}. Flags stick between checks."""

    def __init__(self, emails, keywords=True, sizes=None, broken=()):
        self.emails = {num: m if isinstance(m, bytes) else m.as_bytes() for num, m in emails.items()}
        self.flags = {num: set() for num in self.emails}
        self.keywords = keywords
        self.sizes = sizes or {}
        self.broken = broken  # emails the server won't hand over
        self.fetched = []
        self.searched = None
        self.ssl_context = None

    def __call__(self, host, port, ssl_context=None, timeout=None):
        self.ssl_context = ssl_context
        return self

    def login(self, user, password):
        pass

    def select(self, folder):
        return "OK", [str(len(self.emails)).encode()]

    def search(self, charset, *criteria):
        self.searched = criteria
        return "OK", [b" ".join(n for n in self.emails if not self.flags[n] & {"\\Seen", FAILED})]

    def fetch(self, num, what):
        self.fetched.append((num, what))
        if num in self.broken:
            return "NO", [b"[UNAVAILABLE] Internal error occurred"]
        raw = self.emails[num]
        if "HEADER.FIELDS" in what:
            head = re.split(rb"\r?\n\r?\n", raw, maxsplit=1)[0] + b"\n\n"
            size = self.sizes.get(num, len(raw))
            return "OK", [(num + b" (RFC822.SIZE %d BODY[HEADER.FIELDS (FROM SUBJECT AUTHENTICATION-RESULTS)]<0> {%d}"
                           % (size, len(head)), head), b")"]
        return "OK", [(num + b" (BODY[] {%d}" % len(raw), raw), b")"]

    def store(self, num, flags, value):
        if value == FAILED and not self.keywords:
            return "NO", [b"[CANNOT] No permanent keywords"]
        self.flags[num].add(value)
        return "OK", [b""]

    def logout(self):
        pass


def check(imap, box=None, send=None):
    sent = []
    with mock.patch("imaplib.IMAP4_SSL", imap):
        count = (box or inbox(subject="New contact", fields=["Name"])).check(send or sent.append)
    return count, sent


class CheckTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_sends_and_marks_as_read(self):
        imap = FakeImap({b"1": make_email("Name: Ana", subject="New contact: Ana"),
                         b"2": make_email("spam", subject="Newsletter")})
        count, sent = check(imap)
        self.assertEqual(count, 1)
        self.assertEqual(imap.flags, {b"1": {"\\Seen"}, b"2": {FAILED}})  # loose server match: skipped, not refetched
        self.assertEqual(sent, ["📬 New contact from your website\n\nName: Ana"])
        self.assertEqual(imap.searched, ("UNSEEN", "UNKEYWORD", FAILED, "SUBJECT", '"New contact"'))

    def test_the_server_certificate_is_checked(self):
        imap = FakeImap({})
        check(imap)
        self.assertEqual(imap.ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(imap.ssl_context.check_hostname)

    def test_a_broken_email_never_holds_up_the_rest(self):
        nested = b"--b0\n" + b"".join(b'Content-Type: multipart/mixed; boundary="b%d"\n\n--b%d\n' % (i, i)
                                      for i in range(1, 3000)) + b"Content-Type: text/plain\n\nName: deep\n"
        imap = FakeImap({
            b"1": raw_email('text/plain; charset="x-no-such-charset"', b"Name: Unknown \xff charset\n"),
            b"2": raw_email('text/plain; charset=""', b"Name: Empty charset\n"),
            # Deep enough to exhaust the parser's stack; its subject hides a line break and is far too long.
            b"3": raw_email('multipart/mixed; boundary="b0"', nested,
                            subject="=?utf-8?q?New_contact=3A_deep=0Anesting?= " + "x" * 300),
            b"4": raw_email("multipart/mixed", b"Name: no boundary\n"),
            b"5": make_email("Name: Good", subject="New contact: good"),
        })
        with self.assertLogs("inbox", level="INFO"):
            count, sent = check(imap)
        self.assertEqual(len(sent), 5)
        self.assertIn("Name: Unknown � charset", sent[0])
        self.assertIn("Name: Empty charset", sent[1])
        self.assertEqual(sent[4], "📬 New contact from your website\n\nName: Good")
        for num, flags in imap.flags.items():
            self.assertTrue(flags & {"\\Seen", FAILED}, num)  # every one is done with: none comes back
        for text in sent:
            if "could not be forwarded" in text:
                subject = text.splitlines()[1]
                self.assertLessEqual(len(subject), len("Subject: ") + 101)
                self.assertNotIn("\n", subject)
        self.assertGreaterEqual(count, 3)

    def test_only_email_from_the_website_is_forwarded(self):
        forged = "mx.example.net; dkim=fail header.d=example.com"
        imap = FakeImap({
            b"1": make_email("Name: Wrong sender", subject="New contact", sender="web@evil.example"),
            b"2": make_email("Name: Display name trick", subject="New contact",
                             sender='"web@example.com" <attacker@evil.example>'),
            b"3": make_email("Name: No DKIM", subject="New contact", auth=None),
            b"4": make_email("Name: Other domain", subject="New contact",
                             auth="mx.example.net; dkim=pass header.d=evil.example"),
            b"5": make_email("Name: Forged below", subject="New contact", auth=forged),
            b"6": make_email("Name: Real", subject="New contact"),
        })
        # The sender's own (fake) header ends up below the one the mailbox server adds on top.
        imap.emails[b"5"] = imap.emails[b"5"].replace(b"Subject:", b"Authentication-Results: " + DKIM_OK.encode()
                                                      + b"\nSubject:", 1)
        with self.assertLogs("inbox", level="INFO"):
            count, sent = check(imap)
        self.assertEqual(count, 1)
        self.assertEqual(sent[0], "📬 New contact from your website\n\nName: Real")
        self.assertIn("Not forwarded: 5 email(s)", sent[1])
        self.assertEqual(len(sent), 2)
        self.assertEqual({n for n, f in imap.flags.items() if f == {FAILED}}, {b"1", b"2", b"3", b"4", b"5"})
        self.assertFalse(any(what == "(BODY.PEEK[])" for num, what in imap.fetched if num != b"6"))

    def test_dkim_header_i_and_checks_switched_off(self):
        gmail_style = "mx.example.net; dkim=pass header.i=@example.com header.s=s1"
        count, _ = check(FakeImap({b"1": make_email("Name: A", subject="New contact", auth=gmail_style)}))
        self.assertEqual(count, 1)
        anyone = FakeImap({b"1": make_email("Name: B", subject="New contact", sender="any@else.example", auth=None)})
        count, _ = check(anyone, inbox(subject="New contact", sender="", dkim_domain=""))
        self.assertEqual(count, 1)

    def test_too_big_is_not_downloaded(self):
        imap = FakeImap({b"1": make_email("Name: Big", subject="New contact: big")}, sizes={b"1": 50 * 1024 * 1024})
        with self.assertLogs("inbox", level="INFO"):
            count, sent = check(imap)
        self.assertEqual(count, 0)
        self.assertEqual(sent, ["⚠️ A form email is too big to forward (50.0 MB).\nSubject: New contact: big\n"
                                "Read it in the mailbox."])
        self.assertEqual(imap.flags[b"1"], {FAILED})
        self.assertNotIn((b"1", "(BODY.PEEK[])"), imap.fetched)

    def test_a_few_per_check(self):
        imap = FakeImap({str(i).encode(): make_email(f"Name: {i}", subject="New contact") for i in range(1, 16)})
        self.assertEqual(check(imap)[0], inbox_module.MAX_PER_CHECK)
        self.assertEqual(check(imap)[0], 15 - inbox_module.MAX_PER_CHECK)

    def test_telegram_down_leaves_the_email_for_the_next_check(self):
        imap = FakeImap({b"1": make_email("Name: Ana", subject="New contact")})

        def send(text):
            raise telegram.TelegramError("sendMessage: timed out")

        with self.assertLogs("inbox", level="WARNING"), self.assertRaises(ForwardError):
            check(imap, send=send)
        self.assertEqual(imap.flags[b"1"], set())

    def test_an_email_telegram_refuses_gets_a_notice(self):
        imap = FakeImap({b"1": make_email("Name: Ana", subject="New contact: Ana")})
        sent = []

        def send(text):
            if "Name: Ana" in text:
                raise telegram.TelegramError("sendMessage: HTTP 400 Bad Request")
            sent.append(text)

        with self.assertLogs("inbox", level="WARNING"):
            check(imap, send=send)
        self.assertEqual(sent, ["⚠️ A form email could not be forwarded.\nSubject: New contact: Ana\nRead it in the mailbox."])
        self.assertEqual(imap.flags[b"1"], {FAILED})

    def test_an_email_the_server_wont_hand_over(self):
        imap = FakeImap({b"1": make_email("Name: A", subject="New contact"),
                         b"2": make_email("Name: B", subject="New contact")}, broken={b"1"})
        with self.assertLogs("inbox", level="WARNING"):
            count, sent = check(imap)
        self.assertEqual(count, 1)
        self.assertEqual(sent, ["⚠️ A form email could not be forwarded.\nSubject: ?\nRead it in the mailbox.",
                                "📬 New contact from your website\n\nName: B"])
        self.assertEqual(imap.flags, {b"1": {FAILED}, b"2": {"\\Seen"}})

    def test_a_server_without_keywords_marks_it_as_read(self):
        imap = FakeImap({b"1": make_email("Name: X", subject="New contact", sender="web@evil.example")}, keywords=False)
        with self.assertLogs("inbox", level="INFO"):
            check(imap)
        self.assertEqual(imap.flags[b"1"], {"\\Seen"})


class FakeTelegram:
    def __init__(self):
        self.texts = []
        self.extra = []

    def send(self, chat_id, text, **extra):
        self.texts.append(text)
        self.extra.append(extra)


class BrokenInbox:
    user = "contact@example.com"

    def __init__(self, error=None):
        self.error = error

    def check(self, send):
        if self.error:
            raise self.error
        return 0


class WatcherTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_alerts_once_after_several_failures_and_on_recovery(self):
        box, tg = BrokenInbox(OSError("login failed\nInjected: line")), FakeTelegram()
        watcher = form_to_telegram.Watcher(box, tg, 42, failures_before_alert=3)
        with self.assertLogs("form-to-telegram", level="WARNING") as logs:
            for _ in range(5):
                watcher.check_once()
        self.assertEqual(len(tg.texts), 1)
        self.assertIn("Can't read the mailbox", tg.texts[0])
        self.assertIn("OSError", tg.texts[0])
        self.assertFalse(any("\n" in line for line in logs.output))
        box.error = None
        watcher.check_once()
        watcher.check_once()
        self.assertEqual(len(tg.texts), 2)
        self.assertIn("again", tg.texts[1])

    def test_telegram_failing_is_not_the_mailbox_failing(self):
        box, tg = BrokenInbox(ForwardError("TelegramError: 'timed out'")), FakeTelegram()
        watcher = form_to_telegram.Watcher(box, tg, 42, failures_before_alert=1)
        with self.assertLogs("form-to-telegram", level="WARNING"):
            watcher.check_once()
        self.assertEqual((watcher.failures, tg.texts), (0, []))

    def test_no_link_previews(self):
        tg = FakeTelegram()
        form_to_telegram.Watcher(BrokenInbox(), tg, 42).send("https://example.com")
        self.assertEqual(tg.extra, [{"link_preview_options": {"is_disabled": True}}])

    def test_build_from_config(self):
        values = {"TELEGRAM_CHAT_ID": "42", "BOT_TOKEN": "123:TEST", "IMAP_HOST": "imap.example.com",
                  "IMAP_USER": "u", "IMAP_PASSWORD": "p", "FIELDS": "Name, Email", "LANGUAGE": "es",
                  "FORM_FROM": "Web@Example.com"}
        watcher = form_to_telegram.build(config.Config(values))
        self.assertEqual(watcher.inbox.fields, ["Name", "Email"])
        self.assertEqual(watcher.chat_id, 42)
        self.assertEqual((watcher.inbox.sender, watcher.inbox.dkim_domain), ("web@example.com", "example.com"))
        for extra, expected in (({"DKIM_DOMAIN": "off"}, ("web@example.com", "")),
                                ({"DKIM_DOMAIN": "mail.example.com"}, ("web@example.com", "mail.example.com")),
                                ({"FORM_FROM": "any"}, ("", ""))):
            box = form_to_telegram.build(config.Config({**values, **extra})).inbox
            self.assertEqual((box.sender, box.dkim_domain), expected, extra)
        for broken in ({"FORM_FROM": ""}, {"FORM_FROM": "example.com"}, {"TELEGRAM_CHAT_ID": ""}):
            with self.assertRaises(config.ConfigError, msg=broken):
                form_to_telegram.build(config.Config({**values, **broken}))
        with self.assertRaises(telegram.TelegramError):
            form_to_telegram.build(config.Config({**values, "BOT_TOKEN": "REPLACE_ME"}))

    def test_errors_are_one_short_line(self):
        text = inbox_module.describe(ValueError("bad\r\nInjected: " + "x" * 500))
        self.assertTrue(text.startswith("ValueError: "))
        self.assertNotIn("\n", text)
        self.assertLessEqual(len(text), len("ValueError: ") + 200)


class MessagesTest(unittest.TestCase):
    def test_same_keys_and_placeholders(self):
        def fields(text):
            return {name for _, name, _, _ in string.Formatter().parse(text) if name}

        for key, text in messages.TEXTS["en"].items():
            self.assertEqual(fields(messages.TEXTS["es"][key]), fields(text), key)
        self.assertEqual(set(messages.TEXTS["es"]), set(messages.TEXTS["en"]))


if __name__ == "__main__":
    unittest.main()
