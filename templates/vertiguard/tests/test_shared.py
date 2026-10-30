"""Tests for the shared modules (config, telegram, scheduler, state, gemini)."""

import io
import json
import os
import string
import tempfile
import unittest
import urllib.error
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import config
import gemini
import messages
import scheduler
import telegram
from state import State

TZ = ZoneInfo("Europe/Madrid")


class ConfigTest(unittest.TestCase):
    def load(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.remove, f.name)
        return config.load(f.name)

    def test_parsing(self):
        cfg = self.load("# comment\nA=1\nB = two=2\n\nEMPTY=\nLIST=a, b,,c\n")
        self.assertEqual(cfg.need("A"), "1")
        self.assertEqual(cfg["B"], " two=2")
        self.assertEqual(cfg.get_int("A", 0), 1)
        self.assertEqual(cfg.get_int("EMPTY", 7), 7)
        self.assertEqual(cfg.get_list("LIST"), ["a", "b", "c"])
        self.assertEqual(cfg.get_str("MISSING", "x"), "x")

    def test_errors(self):
        cfg = self.load("EMPTY=\nN=abc\n")
        with self.assertRaises(config.ConfigError):
            cfg.need("EMPTY")
        with self.assertRaises(config.ConfigError):
            cfg.get_int("N", 0)


class SchedulerTest(unittest.TestCase):
    def test_every_aligns_to_the_clock(self):
        nxt = scheduler.every(300)(datetime(2026, 10, 30, 10, 2, 30, tzinfo=TZ))
        self.assertEqual((nxt.hour, nxt.minute, nxt.second), (10, 5, 0))

    def test_daily_at(self):
        at9 = scheduler.daily_at(9)
        self.assertEqual(at9(datetime(2026, 10, 30, 8, 0, tzinfo=TZ)), datetime(2026, 10, 30, 9, 0, tzinfo=TZ))
        self.assertEqual(at9(datetime(2026, 10, 30, 9, 0, tzinfo=TZ)), datetime(2026, 10, 31, 9, 0, tzinfo=TZ))
        monday = scheduler.daily_at(9, weekday=0)(datetime(2026, 10, 30, 12, 0, tzinfo=TZ))  # a Friday
        self.assertEqual((monday.weekday(), monday.day, monday.month), (0, 2, 11))

    def test_failure_and_recovery_reported_once(self):
        events = []
        s = scheduler.Scheduler(TZ, on_failure=lambda n, e: events.append(("fail", n, str(e))),
                                on_recovery=lambda n: events.append(("ok", n)))

        def broken():
            raise RuntimeError("boom")

        with self.assertLogs("scheduler", level="ERROR"):
            s.run("job", broken)
            s.run("job", broken)
        s.run("job", lambda: None)
        s.run("job", lambda: None)
        self.assertEqual(events, [("fail", "job", "boom"), ("ok", "job")])


class StateTest(unittest.TestCase):
    def test_survives_a_restart(self):
        path = os.path.join(tempfile.mkdtemp(), "state.json")
        State(path).set("k", [1, "ñ"])
        self.assertEqual(State(path).get("k"), [1, "ñ"])
        self.assertEqual(State(path + ".missing").get("k", "default"), "default")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body):
    return urllib.error.HTTPError("https://api.telegram.org/botSECRET/x", code, "err", {}, io.BytesIO(body.encode()))


class TelegramTest(unittest.TestCase):
    def test_markdown_falls_back_to_plain_text(self):
        sent = []

        def urlopen(req, timeout):
            body = json.loads(req.data)
            sent.append(body)
            if "parse_mode" in body:
                raise http_error(400, '{"description":"Bad Request: can\'t parse entities"}')
            return FakeResponse(b'{"ok":true,"result":{}}')

        with mock.patch("urllib.request.urlopen", urlopen), self.assertLogs("telegram", level="WARNING"):
            telegram.Telegram("SECRET").send(1, "a_b", markdown=True)
        self.assertEqual(len(sent), 2)
        self.assertNotIn("parse_mode", sent[1])

    def test_errors_do_not_leak_the_token(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(401, "Unauthorized")):
            with self.assertRaises(telegram.TelegramError) as ctx:
                telegram.Telegram("SECRET").call("getMe")
        self.assertNotIn("SECRET", str(ctx.exception))

    def test_updates_removes_a_leftover_webhook(self):
        calls = []

        def urlopen(req, timeout):
            calls.append(req.full_url.rsplit("/", 1)[1])
            if calls[-1] == "getUpdates":
                raise http_error(409, "Conflict: can't use getUpdates method while webhook is active")
            return FakeResponse(b'{"ok":true,"result":true}')

        with mock.patch("urllib.request.urlopen", urlopen), self.assertLogs("telegram", level="INFO"):
            self.assertEqual(telegram.Telegram("SECRET").updates(0), [])
        self.assertEqual(calls, ["getUpdates", "deleteWebhook"])

    def test_md_escapes(self):
        self.assertEqual(telegram.md("a_b*c`d[e"), "a\\_b\\*c\\`d\\[e")


class GeminiTest(unittest.TestCase):
    def test_blocked_response(self):
        with self.assertRaises(gemini.GeminiError):
            gemini.answer_text({"promptFeedback": {"blockReason": "SAFETY"}})

    def test_answer_skips_thoughts(self):
        response = {"candidates": [{"content": {"parts": [{"text": "hidden", "thought": True}, {"text": " hi "}]}}]}
        self.assertEqual(gemini.answer_text(response), "hi")


class MessagesTest(unittest.TestCase):
    def test_same_keys_and_placeholders_in_every_language(self):
        def fields(text):
            return {name for _, name, _, _ in string.Formatter().parse(text) if name}

        english = messages.TEXTS["en"]
        for language, texts in messages.TEXTS.items():
            self.assertEqual(set(texts), set(english), language)
            for key, text in texts.items():
                self.assertEqual(fields(text), fields(english[key]), f"{language}.{key}")

    def test_unknown_language(self):
        with self.assertRaises(ValueError):
            messages.set_language("fr")


if __name__ == "__main__":
    unittest.main()
