import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import config  # noqa: E402
import toolkit  # noqa: E402
from config import Config, ConfigError  # noqa: E402
from state import State  # noqa: E402

TELEGRAM = dict(TELEGRAM_BOT_TOKEN="123456:TEST_TOKEN", TELEGRAM_CHAT_ID="YOUR_CHAT_ID")
SITES = dict(UPTIME_SITES="Client A|https://example.com")
PLAUSIBLE = dict(PLAUSIBLE_SITE_ID="example.com", PLAUSIBLE_API_KEY="TEST_KEY", REPORT_TO="client@example.com")
SMTP = dict(SMTP_HOST="smtp.example.com", SMTP_FROM="reports@example.com")
GOTENBERG = dict(GOTENBERG_URL="http://localhost:3000")
EVERYTHING = Config(**TELEGRAM, **SITES, **PLAUSIBLE, **SMTP, **GOTENBERG)


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send(self, chat_id, text, **extra):
        self.sent.append((chat_id, text))


class FeaturesTest(unittest.TestCase):
    def test_everything_off_when_nothing_is_set(self):
        missing = toolkit.features(Config())
        self.assertEqual(missing["uptime"], ["UPTIME_SITES", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
        self.assertEqual(missing["report"], ["PLAUSIBLE_SITE_ID", "PLAUSIBLE_API_KEY", "REPORT_TO",
                                             "SMTP_HOST", "SMTP_FROM"])
        self.assertEqual(missing["invoices"], ["GOTENBERG_URL", "SMTP_HOST", "SMTP_FROM"])

    def test_everything_on(self):
        self.assertEqual(toolkit.features(EVERYTHING), {"uptime": [], "report": [], "invoices": []})

    def test_each_feature_needs_its_own_settings(self):
        missing = toolkit.features(Config(**SITES, **PLAUSIBLE, **GOTENBERG))
        self.assertEqual(missing["uptime"], ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
        self.assertEqual(missing["report"], ["SMTP_HOST", "SMTP_FROM"])
        self.assertEqual(missing["invoices"], ["SMTP_HOST", "SMTP_FROM"])

        missing = toolkit.features(Config(**TELEGRAM, **SMTP))
        self.assertEqual(missing["uptime"], ["UPTIME_SITES"])
        self.assertEqual(missing["report"], ["PLAUSIBLE_SITE_ID", "PLAUSIBLE_API_KEY", "REPORT_TO"])
        self.assertEqual(missing["invoices"], ["GOTENBERG_URL"])

    def test_blank_values_count_as_not_set(self):
        missing = toolkit.features(Config(EVERYTHING, UPTIME_SITES=" , ", SMTP_HOST="  "))
        self.assertEqual(missing["uptime"], ["UPTIME_SITES"])
        self.assertIn("SMTP_HOST", missing["report"])


class ExampleConfigTest(unittest.TestCase):
    PATH = os.path.join(os.path.dirname(__file__), "..", "agency-toolkit.env.example")

    def test_a_fresh_install_has_everything_off(self):
        missing = toolkit.features(config.load(self.PATH))
        self.assertTrue(all(missing.values()), missing)

    def test_filled_in_it_turns_everything_on(self):
        settings = config.load(self.PATH)
        settings.update(EVERYTHING)
        self.assertEqual(toolkit.features(settings), {"uptime": [], "report": [], "invoices": []})
        with tempfile.TemporaryDirectory() as tmp, self.assertLogs("toolkit", "INFO"):
            jobs = toolkit.build(settings, State(os.path.join(tmp, "state.json")), FakeTelegram())
        self.assertEqual(len(jobs.jobs), 2)


class BuildTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = State(os.path.join(tmp.name, "state.json"))
        self.telegram = FakeTelegram()

    def build(self, settings):
        return toolkit.build(settings, self.state, self.telegram)

    def test_jobs_follow_the_settings(self):
        with self.assertLogs("toolkit", "INFO") as logs:
            self.assertEqual([name for name, _, _ in self.build(EVERYTHING).jobs], ["uptime", "report"])
        text = "\n".join(logs.output)
        self.assertIn("Uptime monitor: on (1 site(s), every 5 min)", text)
        self.assertIn("Weekly report: on (plausible, mon at 09:00, to client@example.com)", text)
        self.assertIn("Invoices (invoice.py): ready", text)

    def test_nothing_set(self):
        with self.assertLogs("toolkit", "INFO") as logs:
            jobs = toolkit.build(Config(), self.state)
        self.assertEqual(jobs.jobs, [])
        self.assertIsNone(jobs.on_failure)
        text = "\n".join(logs.output)
        self.assertIn("Uptime monitor: off (set UPTIME_SITES, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)", text)
        self.assertIn("Invoices (invoice.py): off (set GOTENBERG_URL, SMTP_HOST, SMTP_FROM)", text)
        self.assertIn("No scheduled feature is on", text)

    def test_only_the_report(self):
        with self.assertLogs("toolkit", "INFO"):
            jobs = self.build(Config(**PLAUSIBLE, **SMTP))
        self.assertEqual([name for name, _, _ in jobs.jobs], ["report"])

    def test_wrong_settings_fail_at_startup(self):
        for change in (dict(LANGUAGE="fr"), dict(UPTIME_SITES="example.com"), dict(UPTIME_INTERVAL_MINUTES="0"),
                       dict(REPORT_DAY="someday"), dict(REPORT_DAYS="0"), dict(ANALYTICS_PROVIDER="matomo"),
                       dict(UPTIME_TIMEOUT_SECONDS="ten"), dict(UPTIME_TIMEOUT_SECONDS="0")):
            with self.assertRaises(ConfigError, msg=change), self.assertLogs("toolkit", "INFO"):
                self.build(Config(EVERYTHING, **change))

    def test_job_failures_are_reported_once_per_change(self):
        with self.assertLogs("toolkit", "INFO"):
            jobs = self.build(EVERYTHING)

        def broken():
            raise RuntimeError("Plausible answered HTTP 500")

        with self.assertLogs("scheduler", "ERROR"):
            jobs.run("report", broken)
            jobs.run("report", broken)
        jobs.run("report", lambda: None)
        jobs.run("report", lambda: None)
        self.assertEqual(self.telegram.sent, [
            ("YOUR_CHAT_ID", "⚠️ Agency toolkit: the weekly report is failing.\nPlausible answered HTTP 500"),
            ("YOUR_CHAT_ID", "✅ Agency toolkit: the weekly report works again."),
        ])

    def test_the_uptime_job_alerts_on_telegram(self):
        with self.assertLogs("toolkit", "INFO"):
            jobs = self.build(Config(EVERYTHING, LANGUAGE="es"))
        name, _, job = jobs.jobs[0]
        self.assertEqual(name, "uptime")
        job.__self__.check = lambda url, timeout: (None, "timed out")  # job is the bound Monitor.run
        job()
        self.assertEqual(self.telegram.sent, [
            ("YOUR_CHAT_ID", "⛔ Client A no responde (timed out)\nhttps://example.com"),
        ])


class MainTest(unittest.TestCase):
    def test_usage(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(toolkit.main([]), 2)

    def test_missing_config_file(self):
        with self.assertLogs("toolkit", "ERROR"), mock.patch("logging.basicConfig"):
            self.assertEqual(toolkit.main([os.path.join(tempfile.gettempdir(), "no-such-dir", "x.env")]), 1)


if __name__ == "__main__":
    unittest.main()
