import io
import os
import socket
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import messages  # noqa: E402
import uptime  # noqa: E402
from config import Config, ConfigError  # noqa: E402
from state import State  # noqa: E402

SITES = [("Client A", "https://example.com"), ("Client B", "https://shop.example.org")]


class Response(io.BytesIO):
    def __init__(self, status=200):
        super().__init__(b"ok")
        self.status = status


class ClassifyTest(unittest.TestCase):
    def test_no_response_or_5xx_is_down(self):
        for status in (None, 500, 502, 503):
            self.assertEqual(uptime.classify(status), uptime.DOWN, status)

    def test_4xx_is_a_warning(self):
        for status in (400, 403, 404, 429):
            self.assertEqual(uptime.classify(status), uptime.WARNING, status)

    def test_anything_else_is_up(self):
        for status in (200, 204, 301, 399):
            self.assertEqual(uptime.classify(status), uptime.UP, status)


class SitesTest(unittest.TestCase):
    def test_labels_and_bare_urls(self):
        settings = Config(UPTIME_SITES="Client A|https://example.com, https://example.net/health ,")
        self.assertEqual(
            uptime.parse_sites(settings),
            [("Client A", "https://example.com"), ("https://example.net/health", "https://example.net/health")],
        )

    def test_rejects_something_that_is_not_a_url(self):
        with self.assertRaises(ConfigError):
            uptime.parse_sites(Config(UPTIME_SITES="Client A|example.com"))


class CheckTest(unittest.TestCase):
    def test_answer(self):
        with mock.patch("urllib.request.urlopen", return_value=Response(200)) as urlopen:
            self.assertEqual(uptime.check("https://example.com", 10), (200, None))
        req = urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://example.com")
        self.assertIn("agency-toolkit", req.get_header("User-agent"))
        self.assertEqual(urlopen.call_args[1]["timeout"], 10)

    def test_http_error_is_a_status(self):
        error = urllib.error.HTTPError("https://example.com", 503, "Unavailable", {}, io.BytesIO())
        with mock.patch("urllib.request.urlopen", side_effect=error):
            self.assertEqual(uptime.check("https://example.com", 10), (503, None))

    def test_no_answer(self):
        for error, reason in (
            (urllib.error.URLError("Name or service not known"), "Name or service not known"),
            (socket.timeout("timed out"), "timed out"),
        ):
            with mock.patch("urllib.request.urlopen", side_effect=error):
                self.assertEqual(uptime.check("https://example.com", 10), (None, reason))


class MonitorTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "state.json")
        self.status = {url: 200 for _, url in SITES}
        self.sent = []

    def fake_check(self, url, timeout):
        status = self.status[url]
        return (None, "timed out") if status is None else (status, None)

    def monitor(self, sites=SITES, alert=None, language="en"):
        return uptime.Monitor(
            sites, alert or self.sent.append, State(self.path), messages.load(language), check=self.fake_check
        )

    def test_healthy_sites_are_silent(self):
        self.monitor().run()
        self.assertEqual(self.sent, [])

    def test_alerts_only_when_the_status_changes(self):
        monitor = self.monitor()
        self.status["https://example.com"] = 503
        monitor.run()
        monitor.run()
        self.status["https://example.com"] = 502  # Still down: no new alert.
        monitor.run()
        self.assertEqual(self.sent, ["⛔ Client A is down: HTTP 503\nhttps://example.com"])

        self.status["https://example.com"] = 200
        monitor.run()
        monitor.run()
        self.assertEqual(self.sent[1:], ["✅ Client A is back up (HTTP 200)\nhttps://example.com"])

    def test_warning_then_down_then_warning(self):
        monitor = self.monitor()
        for status in (404, 404, 500, 403):
            self.status["https://shop.example.org"] = status
            monitor.run()
        self.assertEqual(self.sent, [
            "⚠️ Client B responds with HTTP 404\nhttps://shop.example.org",
            "⛔ Client B is down: HTTP 500\nhttps://shop.example.org",
            "⚠️ Client B responds with HTTP 403\nhttps://shop.example.org",
        ])

    def test_no_response(self):
        self.status["https://example.com"] = None
        self.monitor().run()
        self.assertEqual(self.sent, ["⛔ Client A is not responding (timed out)\nhttps://example.com"])

    def test_a_restart_does_not_repeat_the_alert(self):
        self.status["https://example.com"] = 503
        self.monitor().run()
        self.monitor().run()  # A new process reading the same state file.
        self.assertEqual(len(self.sent), 1)
        self.status["https://example.com"] = 200
        self.monitor().run()
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(self.sent[1].startswith("✅"))

    def test_an_alert_that_could_not_be_sent_is_tried_again(self):
        def broken(text):
            raise OSError("Telegram is unreachable")

        self.status["https://example.com"] = 503
        with self.assertRaises(OSError):
            self.monitor(alert=broken).run()
        self.monitor().run()
        self.assertEqual(self.sent, ["⛔ Client A is down: HTTP 503\nhttps://example.com"])

    def test_sites_removed_from_the_list_are_forgotten(self):
        self.status["https://shop.example.org"] = 503
        self.monitor().run()
        self.monitor(sites=SITES[:1]).run()
        self.assertEqual(State(self.path).get("uptime"), {})

    def test_spanish(self):
        self.status["https://example.com"] = 502
        self.monitor(language="es").run()
        self.assertEqual(self.sent, ["⛔ Client A caído: HTTP 502\nhttps://example.com"])


if __name__ == "__main__":
    unittest.main()
