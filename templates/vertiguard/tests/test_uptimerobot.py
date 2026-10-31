import http.client
import json
import threading
import unittest
import urllib.error
import urllib.request

import messages
import uptimerobot
from tests.fakes import FakeTelegram

TOKEN = "s3cret-webhook-token-0123456789"
PATH = "/webhook/uptimerobot"


class AlertTextTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_down(self):
        text = uptimerobot.alert({"alertType": "1", "monitorFriendlyName": "<my_site>", "monitorURL": "https://example.com"})
        self.assertIn("DOWN", text)
        self.assertIn("Monitor: <b>&lt;my_site&gt;</b>", text)

    def test_up(self):
        self.assertIn("UP again", uptimerobot.alert({"alertTypeFriendlyName": "Up"}))


class FieldsTest(unittest.TestCase):
    def test_json_form_and_query(self):
        self.assertEqual(uptimerobot.fields("a=1", b'{"b": 2}'), {"a": "1", "b": 2})
        self.assertEqual(uptimerobot.fields("", b"b=2&c=3"), {"b": "2", "c": "3"})

    def test_deeply_nested_json_is_not_an_error(self):
        self.assertEqual(uptimerobot.fields("a=1", b"[" * 60000), {"a": "1"})

    def test_too_many_form_fields_are_ignored(self):
        self.assertEqual(uptimerobot.fields("", "&".join(f"k{i}=v" for i in range(500)).encode()), {})


class WebhookServerTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")
        self.tg = FakeTelegram()
        self.server = uptimerobot.server(self.tg, 42, 0, PATH, TOKEN)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, path, body=None, method="POST", headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def raw(self, headers, body=b""):
        """A request with exactly these headers (urllib always adds a correct Content-Length)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.putrequest("POST", PATH, skip_accept_encoding=True)
            for name, value in headers.items():
                conn.putheader(name, value)
            conn.endheaders(body)
            return conn.getresponse().status
        finally:
            conn.close()

    def test_forwards_json_alert_with_the_token_in_the_body(self):
        body = json.dumps({"token": TOKEN, "alertType": 1, "monitorFriendlyName": "Site"}).encode()
        self.assertEqual(self.request(PATH, body), 200)
        self.assertIn("DOWN", self.tg.texts[0])
        self.assertNotIn(TOKEN, self.tg.texts[0])

    def test_token_in_the_query_string_or_a_header(self):
        self.assertEqual(self.request(f"{PATH}/?token={TOKEN}&alertType=2&monitorFriendlyName=Site", b""), 200)
        self.assertIn("UP again", self.tg.texts[0])
        body = json.dumps({"alertType": 1}).encode()
        self.assertEqual(self.request(PATH, body, headers={"X-Webhook-Token": TOKEN}), 200)
        self.assertEqual(len(self.tg.sent), 2)

    def test_missing_or_wrong_token_is_404_and_sends_nothing(self):
        self.assertEqual(self.request(PATH, json.dumps({"alertType": 1}).encode()), 404)
        self.assertEqual(self.request(PATH, json.dumps({"token": TOKEN[:-1], "alertType": 1}).encode()), 404)
        self.assertEqual(self.request(PATH, json.dumps({"token": "\ud800ñ", "alertType": 1}).encode()), 404)
        self.assertEqual(self.request(PATH, json.dumps({"token": [TOKEN]}).encode()), 404)
        self.assertEqual(self.request(f"{PATH}?token=nope", b""), 404)
        self.assertEqual(self.request(PATH, b"{}", headers={"X-Webhook-Token": "nope"}), 404)
        self.assertEqual(self.tg.sent, [])

    def test_other_paths_and_get_are_404(self):
        self.assertEqual(self.request(f"/rest/login?token={TOKEN}", b"{}"), 404)
        self.assertEqual(self.request(f"{PATH}?token={TOKEN}", method="GET"), 404)
        self.assertEqual(self.tg.sent, [])

    def test_bad_content_length(self):
        self.assertEqual(self.raw({}), 400)
        self.assertEqual(self.raw({"Content-Length": "-1"}), 400)
        self.assertEqual(self.raw({"Content-Length": "12abc"}), 400)
        self.assertEqual(self.raw({"Transfer-Encoding": "chunked"}, b"0\r\n\r\n"), 400)
        self.assertEqual(self.raw({"Content-Length": str(uptimerobot.MAX_BODY + 1)}), 413)
        self.assertEqual(self.tg.sent, [])

    def test_the_server_cuts_a_flood(self):
        server = uptimerobot.server(self.tg, 42, 0, PATH + "2", TOKEN, per_minute=2)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        for _ in range(5):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{PATH}2?token={TOKEN}", data=b"{}")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(r.status, 200)
        self.assertEqual(len(self.tg.sent), 2)
        with self.assertLogs("uptimerobot", level="WARNING"):
            server.flood.flush()  # what its timer does when the minute is over
        self.assertEqual(len(self.tg.sent), 3)
        self.assertIn("3 more alerts in a minute were not forwarded (limit: 2 a minute)", self.tg.texts[2])

    def test_short_token_is_refused(self):
        with self.assertRaises(ValueError):
            uptimerobot.server(self.tg, 42, 0, PATH, "short")


class FloodTest(unittest.TestCase):
    def test_cut_and_summed_up_once_a_minute(self):
        reports = []
        clock = [100.0]
        flood = uptimerobot.Flood(2, reports.append, window=60, clock=lambda: clock[0])
        self.assertEqual([flood.allow() for _ in range(5)], [True, True, False, False, False])
        with self.assertLogs("uptimerobot", level="WARNING"):
            flood.flush()  # what the timer does when the minute is over
        self.assertEqual(reports, [3])
        clock[0] += 60
        self.assertTrue(flood.allow())
        flood.flush()
        self.assertEqual(reports, [3])  # nothing dropped since: no second summary

    def test_the_timer_sends_the_summary_when_the_minute_is_over(self):
        reports = []
        done = threading.Event()
        flood = uptimerobot.Flood(1, lambda n: (reports.append(n), done.set()), window=0.2)
        with self.assertLogs("uptimerobot", level="WARNING"):
            self.assertEqual([flood.allow() for _ in range(3)], [True, False, False])
            self.assertTrue(done.wait(5))
        self.assertEqual(reports, [2])


if __name__ == "__main__":
    unittest.main()
