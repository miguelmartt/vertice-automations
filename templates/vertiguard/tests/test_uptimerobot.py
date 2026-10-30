import json
import threading
import unittest
import urllib.error
import urllib.request

import messages
import uptimerobot
from tests.fakes import FakeTelegram


class AlertTextTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_down(self):
        text = uptimerobot.alert({"alertType": "1", "monitorFriendlyName": "<my_site>", "monitorURL": "https://example.com"})
        self.assertIn("DOWN", text)
        self.assertIn("Monitor: <b>&lt;my_site&gt;</b>", text)

    def test_up(self):
        self.assertIn("UP again", uptimerobot.alert({"alertTypeFriendlyName": "Up"}))


class WebhookServerTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")
        self.tg = FakeTelegram()
        self.server = uptimerobot.server(self.tg, 42, 0, "/webhook/uptimerobot")
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, path, body=None, method="POST"):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def test_forwards_json_alert(self):
        body = json.dumps({"alertType": 1, "monitorFriendlyName": "Site"}).encode()
        self.assertEqual(self.request("/webhook/uptimerobot", body), 200)
        self.assertIn("DOWN", self.tg.texts[0])

    def test_query_string_alert(self):
        self.assertEqual(self.request("/webhook/uptimerobot/?alertType=2&monitorFriendlyName=Site", b""), 200)
        self.assertIn("UP again", self.tg.texts[0])

    def test_other_paths_and_get_are_404(self):
        self.assertEqual(self.request("/rest/login", b"{}"), 404)
        self.assertEqual(self.request("/webhook/uptimerobot", method="GET"), 404)
        self.assertEqual(self.tg.sent, [])


if __name__ == "__main__":
    unittest.main()
