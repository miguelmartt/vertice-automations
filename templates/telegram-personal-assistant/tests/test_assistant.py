import io
import json
import os
import re
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import assistant  # noqa: E402
import config  # noqa: E402

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "personal-assistant.env.example")

FULL = {
    "TELEGRAM_BOT_TOKEN": "REPLACE_ME",
    "TELEGRAM_CHAT_ID": "YOUR_CHAT_ID",
    "LANGUAGE": "es",
    "GEMINI_API_KEY": "REPLACE_ME",
    "GOOGLE_CLIENT_ID": "REPLACE_ME",
    "GOOGLE_CLIENT_SECRET": "REPLACE_ME",
    "GOOGLE_REFRESH_TOKEN": "REPLACE_ME",
    "EMAIL_DIGEST_TIME": "08:00",
    "CALENDAR_DIGEST_TIME": "07:30",
    "NEWS_DIGEST_TIME": "08:15",
    "RSS_FEEDS": "https://example.com/feed.xml, https://example.org/rss",
    "SPREADSHEET_ID": "YOUR_SPREADSHEET_ID",
    "EXPENSES_SHEET": "Expenses",
    "READING_SHEET": "Reading list",
}


def make_config(**changes):
    cfg = config.Config(FULL)
    cfg.update(changes)
    return cfg


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send_long(self, chat_id, text):
        self.sent.append((chat_id, text))


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def build(cfg):
    tg = FakeTelegram()
    sched, bot = assistant.build(cfg, tg)
    return tg, sched, bot


class MissingSettingsTest(unittest.TestCase):
    def test_everything_set(self):
        self.assertEqual(assistant.missing_settings(make_config()),
                         {name: [] for name in assistant.FEATURES})

    def test_no_google_turns_off_email_calendar_and_sheets(self):
        missing = assistant.missing_settings(make_config(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="  ",
                                                         GOOGLE_REFRESH_TOKEN=""))
        for name in ("email", "calendar", "expenses", "reading"):
            self.assertIn("GOOGLE_REFRESH_TOKEN", missing[name], name)
        self.assertEqual(missing["news"], [])

    def test_a_half_set_google_lists_what_is_left(self):
        missing = assistant.missing_settings(make_config(GOOGLE_REFRESH_TOKEN=""))
        self.assertEqual(missing["calendar"], ["GOOGLE_REFRESH_TOKEN"])

    def test_no_gemini_turns_off_the_ai_features(self):
        missing = assistant.missing_settings(make_config(GEMINI_API_KEY=""))
        self.assertEqual([name for name, keys in missing.items() if keys], ["email", "news", "reading"])

    def test_empty_feature_settings(self):
        missing = assistant.missing_settings(make_config(
            EMAIL_DIGEST_TIME="", RSS_FEEDS="", SPREADSHEET_ID="", CALENDAR_DIGEST_TIME="07:30"))
        self.assertEqual(missing["email"], ["EMAIL_DIGEST_TIME"])
        self.assertEqual(missing["news"], ["RSS_FEEDS"])
        self.assertEqual(missing["expenses"], ["SPREADSHEET_ID"])
        self.assertEqual(missing["reading"], ["SPREADSHEET_ID"])
        self.assertEqual(missing["calendar"], [])

    def test_only_telegram(self):
        cfg = config.Config(TELEGRAM_BOT_TOKEN="REPLACE_ME", TELEGRAM_CHAT_ID="YOUR_CHAT_ID")
        self.assertTrue(all(assistant.missing_settings(cfg).values()))

    def test_the_example_config_lists_every_setting_and_starts_with_everything_off(self):
        cfg = config.load(EXAMPLE)
        with open(assistant.__file__, encoding="utf-8") as f:
            used = set(re.findall(r'"([A-Z][A-Z_]+)"', f.read())) - {"STATE_DIRECTORY"}
        self.assertEqual(sorted(used - set(cfg)), [])
        self.assertTrue(all(assistant.missing_settings(cfg).values()))
        self.assertEqual(cfg["READING_SHEET"], "Reading list")
        self.assertEqual(cfg["EMAIL_QUERY"], assistant.DEFAULT_EMAIL_QUERY)


class BuildTest(unittest.TestCase):
    def test_everything_on(self):
        _, sched, bot = build(make_config())
        self.assertEqual([name for name, _, _ in sched.jobs], ["calendar", "email", "news"])
        self.assertIsNotNone(bot.expenses)
        self.assertIsNotNone(bot.reading)
        self.assertEqual(bot.daily, [("calendar", "07:30"), ("email", "08:00"), ("news", "08:15")])

    def test_features_off_are_not_built_and_are_logged(self):
        cfg = make_config(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="", GOOGLE_REFRESH_TOKEN="")
        with self.assertLogs("assistant", "INFO") as logs:
            sched, bot = assistant.build(cfg, FakeTelegram())
        self.assertEqual([name for name, _, _ in sched.jobs], ["news"])
        self.assertIsNone(bot.expenses)
        self.assertIsNone(bot.reading)
        lines = [record.getMessage() for record in logs.records]
        self.assertIn("news digest: on, every day at 08:15", lines)
        self.assertIn("expense logger: off (not set: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
                      "GOOGLE_REFRESH_TOKEN)", lines)

    def test_nothing_on_is_a_warning(self):
        cfg = config.Config(TELEGRAM_BOT_TOKEN="REPLACE_ME", TELEGRAM_CHAT_ID="YOUR_CHAT_ID")
        with self.assertLogs("assistant", "WARNING"):
            sched, bot = assistant.build(cfg, FakeTelegram())
        self.assertEqual(sched.jobs, [])

    def test_bad_settings(self):
        for key, value in (("LANGUAGE", "fr"), ("TIMEZONE", "Mars/Olympus"), ("EMAIL_DIGEST_TIME", "8am"),
                           ("CALENDAR_WORK_END", "25:00"), ("TELEGRAM_CHAT_ID", "")):
            with self.subTest(key=key), self.assertRaises(config.ConfigError):
                build(make_config(**{key: value}))

    def test_parse_time(self):
        self.assertEqual(assistant.parse_time("07:30", "X"), (7, 30))
        self.assertEqual(assistant.parse_time("8:05", "X"), (8, 5))
        for value in ("0730", "07:30:00", "24:00", "07:60", "seven"):
            with self.assertRaises(config.ConfigError):
                assistant.parse_time(value, "X")

    def test_a_failing_job_is_reported_once_and_so_is_the_recovery(self):
        tg, sched, _ = build(make_config(TIMEZONE="", CALENDAR_ID="primary"))
        job = next(job for name, _, job in sched.jobs if name == "calendar")
        offline = urllib.error.URLError("Network is unreachable")
        with mock.patch("urllib.request.urlopen", side_effect=offline), self.assertLogs("scheduler", "ERROR"):
            self.assertFalse(sched.run("calendar", job))
            self.assertFalse(sched.run("calendar", job))
        self.assertEqual(tg.sent, [("YOUR_CHAT_ID", "⚠️ Ha fallado la agenda del día: oauth2.googleapis.com/token: "
                                                    "Network is unreachable\nTe aviso cuando vuelva a funcionar.")])

        answers = [{"access_token": "x", "expires_in": 3600}, {"items": []}]
        with mock.patch("urllib.request.urlopen",
                        side_effect=lambda req, timeout: FakeResponse(json.dumps(answers.pop(0)).encode())):
            self.assertTrue(sched.run("calendar", job))
        self.assertTrue(tg.sent[1][1].startswith("🗓️ Agenda de hoy"))
        self.assertEqual(tg.sent[2][1], "✅ Vuelve a funcionar la agenda del día.")


class MainTest(unittest.TestCase):
    def test_usage(self):
        with mock.patch("sys.stderr", io.StringIO()) as err:
            self.assertEqual(assistant.main([]), 2)
        self.assertIn("Usage", err.getvalue())

    def test_a_missing_config_file_is_an_error(self):
        with mock.patch("logging.basicConfig"), self.assertLogs("assistant", "ERROR"):
            self.assertEqual(assistant.main(["/nonexistent/personal-assistant.env"]), 1)


if __name__ == "__main__":
    unittest.main()
