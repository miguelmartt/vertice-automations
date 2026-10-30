import email.message
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import reading  # noqa: E402
import web  # noqa: E402
from messages import Messages  # noqa: E402

NOW = datetime(2026, 10, 30, 21, 5, 9, 123, tzinfo=timezone(timedelta(hours=1)))

PAGE = """<!doctype html>
<html><head>
  <meta charset="utf-8">
  <title>
     An   article &amp; more </title>
  <style>body { color: red }</style>
  <script>var secret = "<p>not text</p>";</script>
</head>
<body>
  <nav>Menu</nav>
  <article><h1>Heading</h1><p>First&nbsp;paragraph with <a href="/x">a link</a>.</p>
  <svg><title>icon</title><text>chart</text></svg>
  <noscript>Enable JavaScript</noscript>
  <p>Caf&eacute; &#8364;5</p></article>
</body></html>"""


class FakeSheets:
    def __init__(self):
        self.appended = []

    def append(self, sheet, row):
        self.appended.append((sheet, row))


class FakeAI:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return "Summary.\n- one\n- two\n- three\ntags: a, b, c"


class PageTextTest(unittest.TestCase):
    def test_title_and_visible_text(self):
        title, text = reading.page_text(PAGE)
        self.assertEqual(title, "An article & more")
        self.assertEqual(text, "Menu Heading First paragraph with a link . Café €5")

    def test_text_is_capped(self):
        _, text = reading.page_text("<p>" + "word " * 5000 + "</p>")
        self.assertEqual(len(text), reading.MAX_TEXT)

    def test_no_title(self):
        self.assertEqual(reading.page_text("<p>Hi</p>"), ("", "Hi"))

    def test_decode(self):
        latin = '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"><p>Caf\xe9</p>'
        self.assertIn("Café", reading.decode(latin.encode("latin-1"), None))
        self.assertEqual(reading.decode("Café".encode("utf-8"), None), "Café")
        self.assertEqual(reading.decode("Café".encode("cp1252"), "windows-1252"), "Café")
        self.assertEqual(reading.decode(b"abc", "no-such-charset"), "abc")

    def test_only_web_pages_are_read(self):
        def fetch(url, max_bytes):
            return b"%PDF-1.7 ...", "application/pdf", None
        self.assertEqual(reading.read_page("https://example.com/file.pdf", fetch), ("", ""))


class ReadItLaterTest(unittest.TestCase):
    def setUp(self):
        self.sheets, self.ai = FakeSheets(), FakeAI()

    def save(self, fetch, language="en"):
        later = reading.ReadItLater(self.sheets, "Reading list", self.ai, Messages(language), lambda: NOW, fetch)
        return later.save("https://example.com/post")

    def test_summarizes_saves_and_replies(self):
        def fetch(url, max_bytes):
            self.assertEqual(max_bytes, reading.MAX_PAGE_BYTES)
            return PAGE.encode(), "text/html", "utf-8"

        reply = self.save(fetch, "es")
        self.assertEqual(reply, "📑 Guardado: An article & more\n\n" + FakeAI().ask(""))
        self.assertEqual(self.sheets.appended, [("Reading list", [
            "2026-10-30T21:05:09+01:00", "An article & more", "https://example.com/post", FakeAI().ask("")])])
        prompt = self.ai.prompts[0]
        self.assertIn("Write it in Spanish (Spain).", prompt)
        self.assertIn("Title: An article & more\nURL: https://example.com/post", prompt)
        self.assertIn("Café €5", prompt)

    def test_a_page_that_cannot_be_read_is_saved_anyway(self):
        def fetch(url, max_bytes):
            raise web.FetchError("HTTP 403")

        with self.assertLogs("reading", "WARNING"):
            reply = self.save(fetch)
        self.assertEqual(self.ai.prompts, [])
        self.assertEqual(self.sheets.appended[0][1][1:], ["https://example.com/post", "https://example.com/post", ""])
        self.assertTrue(reply.startswith("📑 Saved: https://example.com/post\n\nI couldn't read this page"))

    def test_a_page_without_text(self):
        reply = self.save(lambda url, max_bytes: (b"<html><title>App</title><script>app()</script></html>",
                                                  "text/html", None))
        self.assertEqual(self.ai.prompts, [])
        self.assertTrue(reply.startswith("📑 Saved: App\n\nI couldn't read this page"))


class FakeResponse(io.BytesIO):
    def __init__(self, body, content_type):
        super().__init__(body)
        self.headers = email.message.Message()
        self.headers["Content-Type"] = content_type
        self.asked = None

    def read(self, size=-1):
        self.asked = size
        return super().read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FetchTest(unittest.TestCase):
    def test_reads_at_most_the_cap(self):
        response = FakeResponse(b"x" * 100, "text/html; charset=ISO-8859-1")
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            body, content_type, charset = web.fetch("https://example.com/", 10)
        self.assertEqual((body, content_type, charset), (b"x" * 10, "text/html", "iso-8859-1"))
        self.assertEqual(urlopen.call_args[0][0].get_header("User-agent"), web.USER_AGENT)

    def test_only_http_urls(self):
        for url in ("file:///etc/passwd", "ftp://example.com/x", "example.com"):
            with self.assertRaises(web.FetchError):
                web.fetch(url, 10)

    def test_errors_become_fetch_errors(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(web.FetchError):
                web.fetch("https://example.com/", 10)


if __name__ == "__main__":
    unittest.main()
