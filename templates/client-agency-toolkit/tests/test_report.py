import io
import json
import os
import sys
import unittest
import urllib.error
import urllib.parse
from datetime import date, datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import messages  # noqa: E402
import report  # noqa: E402
from config import Config, ConfigError  # noqa: E402

MONDAY = datetime(2026, 11, 2, 9, 0)

PLAUSIBLE = Config(
    PLAUSIBLE_SITE_ID="example.com",
    PLAUSIBLE_API_KEY="TEST_KEY",
    REPORT_TO="client@example.com",
)


class Response(io.BytesIO):
    status = 200


def query(req):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(req.full_url).query))


class FakeAPI:
    """Answers like the analytics API would, and keeps every request."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        for match, answer in self.answers:
            if match(req):
                if isinstance(answer, Exception):
                    raise answer
                return Response(json.dumps(answer).encode())
        raise AssertionError(f"unexpected request {req.full_url}")


def plausible_api(pages=None, sources=None):
    return FakeAPI([
        (lambda r: "/aggregate" in r.full_url, {"results": {
            "visitors": {"value": 1234}, "pageviews": {"value": 4321},
            "bounce_rate": {"value": 47}, "visit_duration": {"value": 95},
        }}),
        (lambda r: query(r).get("property") == "event:page", {"results": pages if pages is not None else [
            {"page": "/", "visitors": 900}, {"page": "/blog/<script>alert(1)</script>", "visitors": 12},
        ]}),
        (lambda r: query(r).get("property") == "visit:source", {"results": sources if sources is not None else [
            {"source": "Google", "visitors": 500}, {"source": "Direct / None", "visitors": 300},
        ]}),
    ])


class PlausibleTest(unittest.TestCase):
    def build(self, api, language="en", settings=PLAUSIBLE):
        with mock.patch("urllib.request.urlopen", api):
            return report.build(settings, messages.load(language), MONDAY)

    def test_report_html(self):
        subject, page, text = self.build(plausible_api())
        self.assertEqual(subject, "Weekly report — example.com")
        for expected in ("Weekly report · example.com", "Period: 2026-10-26 – 2026-11-01",
                         "1,234", "4,321", "47%", "1m 35s", "Google", "Direct / None", "900"):
            self.assertIn(expected, page)
        self.assertIn("/blog/&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertIn("Visitors: 1,234", text)
        self.assertIn("- Google: 500", text)

    def test_requests(self):
        api = plausible_api()
        self.build(api)
        self.assertEqual(len(api.requests), 3)
        first = api.requests[0]
        self.assertTrue(first.full_url.startswith("https://plausible.io/api/v1/stats/aggregate?"))
        self.assertEqual(first.get_header("Authorization"), "Bearer TEST_KEY")
        self.assertEqual(query(first), {
            "site_id": "example.com", "period": "custom", "date": "2026-10-26,2026-11-01",
            "metrics": "visitors,pageviews,bounce_rate,visit_duration",
        })
        self.assertEqual(query(api.requests[1])["limit"], "5")

    def test_self_hosted_url_and_site_name(self):
        api = plausible_api()
        settings = Config(PLAUSIBLE, PLAUSIBLE_URL="https://stats.example.com/", REPORT_SITE_NAME="Client A")
        subject, _, _ = self.build(api, settings=settings)
        self.assertTrue(api.requests[0].full_url.startswith("https://stats.example.com/api/v1/stats/aggregate?"))
        self.assertEqual(subject, "Weekly report — Client A")

    def test_no_data(self):
        _, page, _ = self.build(plausible_api(pages=[], sources=[]))
        self.assertEqual(page.count("No data"), 2)

    def test_spanish(self):
        subject, page, _ = self.build(plausible_api(), language="es")
        self.assertEqual(subject, "Informe semanal — example.com")
        self.assertIn("Periodo: del 26/10/2026 al 01/11/2026", page)
        self.assertIn("Páginas más vistas", page)
        self.assertIn(">1234<", page)

    def test_api_error(self):
        error = urllib.error.HTTPError("https://plausible.io", 401, "Unauthorized", {}, io.BytesIO(b"bad key"))
        with self.assertRaises(report.ReportError) as raised:
            self.build(FakeAPI([(lambda r: True, error)]))
        self.assertIn("HTTP 401", str(raised.exception))
        self.assertNotIn("TEST_KEY", str(raised.exception))

    def test_send(self):
        with mock.patch("urllib.request.urlopen", plausible_api()), mock.patch.object(report.mailer, "send") as send:
            report.send(Config(PLAUSIBLE, REPORT_TO="a@example.com, b@example.com"), messages.load("en"), MONDAY)
        settings, to, subject, text, page = send.call_args[0]
        self.assertEqual(to, ["a@example.com", "b@example.com"])
        self.assertEqual(subject, "Weekly report — example.com")
        self.assertIn("<html", page)


class UmamiTest(unittest.TestCase):
    SETTINGS = Config(
        ANALYTICS_PROVIDER="umami",
        UMAMI_API_URL="https://umami.example.com/api",
        UMAMI_WEBSITE_ID="WEBSITE_ID",
        UMAMI_API_KEY="TEST_KEY",
        REPORT_TO="client@example.com",
        REPORT_SITE_NAME="example.com",
    )

    def api(self, old_umami=False):
        path_answer = (
            urllib.error.HTTPError("https://umami.example.com", 400, "Bad Request", {}, io.BytesIO())
            if old_umami else [{"x": "/", "y": 40}]
        )
        return FakeAPI([
            (lambda r: "/auth/login" in r.full_url, {"token": "LOGIN_TOKEN"}),
            (lambda r: "/websites/WEBSITE_ID/stats" in r.full_url, {
                "pageviews": 300, "visitors": 100, "visits": 120, "bounces": 60, "totaltime": 7200,
                "comparison": {},
            }),
            (lambda r: query(r).get("type") == "path", path_answer),
            (lambda r: query(r).get("type") == "url", [{"x": "/old", "y": 40}]),
            (lambda r: query(r).get("type") == "referrer", [{"x": "google.com", "y": 30}, {"x": "", "y": 5}]),
        ])

    def build(self, api, settings=None):
        start, end = date(2026, 10, 26), date(2026, 11, 1)
        with mock.patch("urllib.request.urlopen", api):
            stats = report.fetch(settings or self.SETTINGS, start, end, timezone.utc)
        return stats, report.render(stats, "example.com", start, end, messages.load("en"), "Umami")[1]

    def test_report(self):
        api = self.api()
        stats, page = self.build(api)
        self.assertEqual(stats["bounce_rate"], 50)
        self.assertEqual(stats["visit_duration"], 60)
        for expected in ("300", "100", "50%", "1m 0s", "google.com", "(direct)"):
            self.assertIn(expected, page)
        self.assertEqual(query(api.requests[0]), {
            "startAt": str(int(datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp() * 1000)),
            "endAt": str(int(datetime(2026, 11, 2, tzinfo=timezone.utc).timestamp() * 1000) - 1),
        })
        self.assertEqual(api.requests[0].get_header("Authorization"), "Bearer TEST_KEY")

    def test_older_umami_uses_url_for_pages(self):
        stats, _ = self.build(self.api(old_umami=True))
        self.assertEqual(stats["pages"], [("/old", 40.0)])

    def test_login_with_username_and_password(self):
        api = self.api()
        settings = Config(self.SETTINGS, UMAMI_API_KEY="", UMAMI_USERNAME="admin", UMAMI_PASSWORD="secret")
        self.build(api, settings)
        login = api.requests[0]
        self.assertEqual(login.full_url, "https://umami.example.com/api/auth/login")
        self.assertEqual(json.loads(login.data), {"username": "admin", "password": "secret"})
        self.assertEqual(api.requests[1].get_header("Authorization"), "Bearer LOGIN_TOKEN")


class SettingsTest(unittest.TestCase):
    def test_period_is_the_full_days_before_today(self):
        self.assertEqual(report.period(date(2026, 11, 2), 7), (date(2026, 10, 26), date(2026, 11, 1)))
        self.assertEqual(report.period(date(2026, 11, 2), 1), (date(2026, 11, 1), date(2026, 11, 1)))
        with self.assertRaises(ConfigError):
            report.period(date(2026, 11, 2), 0)

    def test_schedule(self):
        self.assertEqual(report.schedule(Config()), (0, 9, 0))
        self.assertEqual(report.schedule(Config(REPORT_DAY="Friday", REPORT_TIME="17:30")), (4, 17, 30))
        for bad in (Config(REPORT_DAY="someday"), Config(REPORT_TIME="25:00"), Config(REPORT_TIME="9")):
            with self.assertRaises(ConfigError):
                report.schedule(bad)

    def test_missing_settings(self):
        self.assertEqual(report.missing_settings(Config()), ["PLAUSIBLE_SITE_ID", "PLAUSIBLE_API_KEY", "REPORT_TO"])
        self.assertEqual(report.missing_settings(PLAUSIBLE), [])
        self.assertEqual(
            report.missing_settings(Config(ANALYTICS_PROVIDER="umami", REPORT_TO="client@example.com")),
            ["UMAMI_API_URL", "UMAMI_WEBSITE_ID", "UMAMI_API_KEY"],
        )
        self.assertEqual(report.missing_settings(UmamiTest.SETTINGS), [])

    def test_unknown_provider(self):
        with self.assertRaises(ConfigError):
            report.provider(Config(ANALYTICS_PROVIDER="matomo"))


if __name__ == "__main__":
    unittest.main()
