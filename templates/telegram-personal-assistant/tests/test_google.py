import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import google  # noqa: E402
import google_auth  # noqa: E402

API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def http_error(url, code, body):
    return urllib.error.HTTPError(url, code, "error", {}, io.BytesIO(json.dumps(body).encode()))


class FakeUrlopen:
    """Stands in for urllib.request.urlopen: records each request and plays the queued answers in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(json.dumps(answer).encode())

    def token_requests(self):
        return [r for r in self.requests if r.full_url == google.TOKEN_URL]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def token(value="access-1", expires_in=3600):
    return {"access_token": value, "expires_in": expires_in, "token_type": "Bearer"}


class GoogleTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.api = google.Google("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN", clock=self.clock)

    def run_with(self, fake, call):
        with mock.patch("urllib.request.urlopen", fake):
            return call()

    def test_refreshes_the_token_then_calls_the_api(self):
        fake = FakeUrlopen(token(), {"items": []})
        self.assertEqual(self.run_with(fake, lambda: self.api.get(API, {"singleEvents": "true"})), {"items": []})
        refresh, call = fake.requests
        self.assertEqual(refresh.full_url, google.TOKEN_URL)
        self.assertEqual(dict(urllib.parse.parse_qsl(refresh.data.decode())), {
            "client_id": "CLIENT_ID", "client_secret": "CLIENT_SECRET",
            "refresh_token": "REFRESH_TOKEN", "grant_type": "refresh_token"})
        self.assertEqual(call.full_url, API + "?singleEvents=true")
        self.assertEqual(call.get_method(), "GET")
        self.assertEqual(call.get_header("Authorization"), "Bearer access-1")

    def test_caches_the_token_until_it_is_about_to_expire(self):
        fake = FakeUrlopen(token("access-1"), {}, {}, token("access-2"), {})
        with mock.patch("urllib.request.urlopen", fake):
            self.api.get(API)
            self.clock.now += 3500  # 100 s left: still good
            self.api.get(API)
            self.clock.now += 50  # 50 s left: renewed before it can expire mid-call
            self.api.get(API)
        self.assertEqual(len(fake.token_requests()), 2)
        self.assertEqual(fake.requests[-1].get_header("Authorization"), "Bearer access-2")

    def test_a_401_gets_a_new_token_once(self):
        fake = FakeUrlopen(token("old"), http_error(API, 401, {"error": {"message": "Invalid Credentials"}}),
                           token("new"), {"ok": True})
        self.assertEqual(self.run_with(fake, lambda: self.api.get(API)), {"ok": True})
        self.assertEqual(fake.requests[-1].get_header("Authorization"), "Bearer new")

    def test_a_second_401_is_an_error(self):
        fake = FakeUrlopen(token(), http_error(API, 401, {}), token(), http_error(API, 401, {}))
        with self.assertRaises(google.GoogleError) as ctx:
            self.run_with(fake, lambda: self.api.get(API))
        self.assertEqual(ctx.exception.status, 401)

    def test_http_errors_say_the_status_and_reason_but_not_the_query(self):
        error = {"error": {"code": 403, "message": "Gmail API has not been used in project"}}
        fake = FakeUrlopen(token(), http_error(API, 403, error))
        with self.assertRaises(google.GoogleError) as ctx:
            self.run_with(fake, lambda: self.api.get(API, {"q": "from:someone"}))
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(str(ctx.exception), "www.googleapis.com/calendar/v3/calendars/primary/events: "
                                             "HTTP 403 Gmail API has not been used in project")

    def test_a_revoked_refresh_token(self):
        error = {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}
        fake = FakeUrlopen(http_error(google.TOKEN_URL, 400, error))
        with self.assertRaises(google.GoogleError) as ctx:
            self.run_with(fake, lambda: self.api.get(API))
        self.assertIn("HTTP 400 invalid_grant: Token has been expired or revoked.", str(ctx.exception))
        self.assertNotIn("REFRESH_TOKEN", str(ctx.exception))

    def test_network_errors(self):
        fake = FakeUrlopen(urllib.error.URLError("Name or service not known"))
        with self.assertRaises(google.GoogleError) as ctx:
            self.run_with(fake, lambda: self.api.get(API))
        self.assertEqual(str(ctx.exception), "oauth2.googleapis.com/token: Name or service not known")

    def test_post_sends_json(self):
        fake = FakeUrlopen(token(), {"updates": {}})
        self.run_with(fake, lambda: self.api.post(API, {"a": [1, "b"]}, {"x": "y"}))
        call = fake.requests[-1]
        self.assertEqual(call.get_method(), "POST")
        self.assertEqual(json.loads(call.data), {"a": [1, "b"]})
        self.assertEqual(call.full_url, API + "?x=y")

    def test_repeated_query_parameters(self):
        fake = FakeUrlopen(token(), {})
        self.run_with(fake, lambda: self.api.get(API, {"metadataHeaders": ["From", "Subject"]}))
        self.assertEqual(fake.requests[-1].full_url, API + "?metadataHeaders=From&metadataHeaders=Subject")


class SheetsTest(unittest.TestCase):
    def test_append_and_read(self):
        fake = FakeUrlopen(token(), {}, {"values": [["Date", "Title"], ["2026-10-30", "x"]]})
        sheets = google.Sheets(google.Google("ID", "SECRET", "REFRESH"), "SPREADSHEET_ID")
        with mock.patch("urllib.request.urlopen", fake):
            sheets.append("Reading list", ["2026-10-30", "=1+1"])
            rows = sheets.rows("Bob's")
        append, read = fake.requests[1:]
        base = google.SHEETS_API + "SPREADSHEET_ID/values/"
        self.assertEqual(append.full_url, base + "%27Reading%20list%27:append"
                                                 "?valueInputOption=RAW&insertDataOption=INSERT_ROWS")
        self.assertEqual(json.loads(append.data), {"values": [["2026-10-30", "=1+1"]]})
        self.assertTrue(read.full_url.startswith(base + "%27Bob%27%27s%27?valueRenderOption=UNFORMATTED_VALUE"))
        self.assertEqual(rows, [["Date", "Title"], ["2026-10-30", "x"]])

    def test_empty_tab(self):
        fake = FakeUrlopen(token(), {"range": "Expenses!A1:Z1000"})
        with mock.patch("urllib.request.urlopen", fake):
            self.assertEqual(google.Sheets(google.Google("ID", "SECRET", "REFRESH"), "S").rows("Expenses"), [])


class GoogleAuthTest(unittest.TestCase):
    def test_pkce(self):
        verifier, challenge = google_auth.pkce_pair()
        self.assertTrue(43 <= len(verifier) <= 128)
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(challenge, expected)

    def test_consent_url(self):
        url = google_auth.consent_url("CLIENT_ID", "http://127.0.0.1:8765", list(google.SCOPES.values()),
                                      "STATE", "CHALLENGE")
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        self.assertEqual(parts.netloc, "accounts.google.com")
        self.assertEqual(query["redirect_uri"], "http://127.0.0.1:8765")
        self.assertEqual(query["access_type"], "offline")
        self.assertEqual(query["code_challenge_method"], "S256")
        self.assertEqual(query["scope"].split(), [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/spreadsheets",
        ])

    def test_reads_a_desktop_client_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "client_secret.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"installed": {"client_id": "ID.apps.example.com", "client_secret": "SECRET"}}, f)
            self.assertEqual(google_auth.read_client(path), ("ID.apps.example.com", "SECRET"))
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"web": {"client_id": "ID", "client_secret": "SECRET"}}, f)
            with self.assertRaises(SystemExit):
                google_auth.read_client(path)


if __name__ == "__main__":
    unittest.main()
