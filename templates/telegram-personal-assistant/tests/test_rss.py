import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import digests  # noqa: E402
import rss  # noqa: E402
import web  # noqa: E402
from messages import Messages  # noqa: E402

NOW = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)

RSS2 = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Example news</title>
    <link>https://example.com/</link>
    <item>
      <title>  First
        story </title>
      <link>https://example.com/1</link>
      <pubDate>Fri, 30 Oct 2026 06:00:00 +0000</pubDate>
      <description>&lt;p&gt;Some &lt;b&gt;bold&lt;/b&gt; text &amp;amp; more&lt;/p&gt;</description>
    </item>
    <item>
      <title>Old story</title>
      <guid>https://example.com/2</guid>
      <pubDate>Mon, 26 Oct 2026 06:00:00 GMT</pubDate>
      <content:encoded><![CDATA[<div>Full text</div>]]></content:encoded>
    </item>
  </channel>
</rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example blog</title>
  <link rel="self" href="https://example.org/atom"/>
  <entry>
    <title type="html">Tom &amp;amp; Jerry</title>
    <link rel="self" href="https://example.org/api/1"/>
    <link rel="alternate" href="https://example.org/posts/1"/>
    <id>tag:example.org,2026:1</id>
    <updated>2026-10-30T07:00:00Z</updated>
    <summary>A short summary</summary>
  </entry>
  <entry>
    <title>No link</title>
    <id>tag:example.org,2026:2</id>
    <published>2026-10-29T09:00:00+02:00</published>
    <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>Rich</p> <p>content</p></div></content>
  </entry>
</feed>"""

RSS1 = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://example.net/"><title>Example</title><link>https://example.net/</link></channel>
  <item rdf:about="https://example.net/a">
    <title>RDF item</title>
    <link>https://example.net/a</link>
    <dc:date>2026-10-30T05:00:00+00:00</dc:date>
  </item>
</rdf:RDF>"""


class FakeAI:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return "the digest"


class ParseTest(unittest.TestCase):
    def test_rss2(self):
        first, old = rss.parse(RSS2)
        self.assertEqual(first.title, "First story")
        self.assertEqual(first.link, "https://example.com/1")
        self.assertEqual(first.date, datetime(2026, 10, 30, 6, 0, tzinfo=timezone.utc))
        self.assertEqual(rss.plain(first.summary), "Some bold text & more")
        self.assertEqual(old.link, "https://example.com/2")  # from the guid
        self.assertEqual(rss.plain(old.summary), "Full text")

    def test_atom(self):
        first, second = rss.parse(ATOM)
        self.assertEqual(first.link, "https://example.org/posts/1")  # rel="alternate", not "self"
        self.assertEqual(first.date, datetime(2026, 10, 30, 7, 0, tzinfo=timezone.utc))
        self.assertEqual(first.summary, "A short summary")
        self.assertEqual(second.link, "tag:example.org,2026:2")
        self.assertEqual(second.date, datetime(2026, 10, 29, 7, 0, tzinfo=timezone.utc))
        self.assertEqual(second.summary, "Rich content")

    def test_rss1(self):
        (item,) = rss.parse(RSS1)
        self.assertEqual((item.title, item.link), ("RDF item", "https://example.net/a"))
        self.assertEqual(item.date, datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc))

    def test_not_a_feed(self):
        with self.assertRaises(rss.FeedError):
            rss.parse(b"<html><body>Not found</body>")

    def test_dates(self):
        self.assertIsNone(rss.parse_date("yesterday"))
        self.assertIsNone(rss.parse_date(""))
        self.assertEqual(rss.parse_date("2026-10-30"), datetime(2026, 10, 30, tzinfo=timezone.utc))


class CompileTest(unittest.TestCase):
    def test_keeps_the_last_24_hours(self):
        text = rss.compile_items(rss.parse(RSS2) + rss.parse(ATOM), NOW)
        self.assertEqual(text, "1. First story\n   Some bold text & more\n   https://example.com/1\n\n"
                               "2. Tom & Jerry\n   A short summary\n   https://example.org/posts/1")

    def test_everything_when_nothing_is_recent(self):
        text = rss.compile_items(rss.parse(RSS2), NOW + timedelta(days=30))
        self.assertIn("1. First story", text)
        self.assertIn("2. Old story", text)

    def test_at_most_40_items_and_short_snippets(self):
        items = [rss.Item("", f"https://example.com/{i}", NOW, "x" * 500) for i in range(50)]
        lines = rss.compile_items(items, NOW).split("\n\n")
        self.assertEqual(len(lines), 40)
        self.assertEqual(lines[0], "1. (no title)\n   " + "x" * 160 + "\n   https://example.com/0")

    def test_no_items(self):
        self.assertEqual(rss.compile_items([], NOW), "")


class NewsDigestTest(unittest.TestCase):
    def fetch(self, feeds):
        def fetch(url, max_bytes):
            body = feeds[url]
            if isinstance(body, Exception):
                raise body
            return body, "application/rss+xml", None
        return fetch

    def test_digest(self):
        ai = FakeAI()
        feeds = {"https://example.com/feed": RSS2, "https://example.org/atom": ATOM}
        text = digests.news_digest(list(feeds), ai, Messages("es"), NOW, self.fetch(feeds))
        self.assertEqual(text, "📰 Resumen de noticias\n\nthe digest")
        self.assertIn("Write it in Spanish (Spain).", ai.prompts[0])
        self.assertIn("1. First story", ai.prompts[0])

    def test_a_broken_feed_is_skipped(self):
        feeds = {"https://example.com/feed": RSS2, "https://example.org/down": web.FetchError("HTTP 503"),
                 "https://example.net/html": b"<html>"}
        with self.assertLogs("digests", "WARNING") as logs:
            text = digests.news_digest(list(feeds), FakeAI(), Messages(), NOW, self.fetch(feeds))
        self.assertEqual(text, "📰 News digest\n\nthe digest")
        self.assertEqual(len(logs.records), 2)

    def test_fails_when_no_feed_can_be_read(self):
        feeds = {"https://example.org/down": web.FetchError("HTTP 503")}
        with self.assertLogs("digests", "WARNING"), self.assertRaises(RuntimeError):
            digests.news_digest(list(feeds), FakeAI(), Messages(), NOW, self.fetch(feeds))

    def test_nothing_new(self):
        ai = FakeAI()
        empty = b"<rss><channel><title>Empty</title></channel></rss>"
        text = digests.news_digest(["https://example.com/feed"], ai, Messages(), NOW,
                                   self.fetch({"https://example.com/feed": empty}))
        self.assertEqual(text, "📰 Nothing new in your feeds today.")
        self.assertEqual(ai.prompts, [])


if __name__ == "__main__":
    unittest.main()
