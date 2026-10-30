import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import digests  # noqa: E402
from messages import Messages  # noqa: E402

MADRID = timezone(timedelta(hours=1))  # a fixed offset: the tests must not depend on the tz database
NOW = datetime(2026, 10, 30, 7, 30, tzinfo=MADRID)


class FakeGoogle:
    """Answers GET calls from a {url: answer or [answers...]} table and records them."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        answer = self.answers[url]
        return answer.pop(0) if isinstance(answer, list) else answer


class FakeAI:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return "the digest"


def gmail_message(sender, subject, snippet):
    return {"snippet": snippet, "payload": {"headers": [
        {"name": "From", "value": sender}, {"name": "Subject", "value": subject}, {"name": "To", "value": "me"}]}}


class EmailDigestTest(unittest.TestCase):
    def google(self):
        return FakeGoogle({
            digests.GMAIL: {"messages": [{"id": "a1"}, {"id": "b2"}], "resultSizeEstimate": 2},
            digests.GMAIL + "/a1": gmail_message("Ana <ana@example.com>", "Invoice", "Hi,  it&#39;s\nattached"),
            digests.GMAIL + "/b2": {"snippet": "", "payload": {"headers": []}},
        })

    def test_digest(self):
        google, ai = self.google(), FakeAI()
        text = digests.email_digest(google, ai, Messages("en"), "newer_than:1d", 25)
        self.assertEqual(text, "📬 Email digest\n\nthe digest")
        self.assertEqual(google.calls[0], (digests.GMAIL, {"q": "newer_than:1d", "maxResults": 25}))
        self.assertEqual(google.calls[1][1], {"format": "metadata", "metadataHeaders": ["From", "Subject"]})
        prompt = ai.prompts[0]
        self.assertIn("Write it in English.", prompt)
        self.assertIn("1. From: Ana <ana@example.com>\n   Subject: Invoice\n   Preview: Hi, it's attached\n\n"
                      "2. From: (unknown sender)\n   Subject: (no subject)\n   Preview: ", prompt)

    def test_no_mail_skips_gemini(self):
        ai = FakeAI()
        google = FakeGoogle({digests.GMAIL: {"resultSizeEstimate": 0}})
        self.assertEqual(digests.email_digest(google, ai, Messages("es"), "q", 25),
                         "📬 No hay correo nuevo en las últimas 24 horas.")
        self.assertEqual(ai.prompts, [])

    def test_preview_is_cut(self):
        text = digests.compile_emails([{"from": "x", "subject": "y", "snippet": "z" * 500}])
        self.assertTrue(text.endswith("Preview: " + "z" * 240))


def event(summary, start, end, location=None):
    item = {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}}
    if location:
        item["location"] = location
    return item


class AgendaTest(unittest.TestCase):
    ITEMS = [
        event("Review", "2026-10-30T12:00:00+01:00", "2026-10-30T13:00:00+01:00"),
        {"summary": "Holiday", "start": {"date": "2026-10-30"}, "end": {"date": "2026-10-31"}},
        event("Stand-up", "2026-10-30T09:00:00Z", "2026-10-30T09:20:00Z", location="Office"),
        event("Call", "2026-10-30T15:00:00+01:00", "2026-10-30T15:15:00+01:00"),
        {"summary": "Cancelled", "start": {}},
    ]

    def test_agenda_and_free_slots(self):
        text = digests.agenda(self.ITEMS, NOW, Messages("es"))
        self.assertEqual(text, "\n".join([
            "🗓️ Agenda de hoy (30/10/2026)",
            "",
            "Tienes 4 evento(s):",
            "",
            "• (todo el día) Holiday",
            "• 10:00–10:20 Stand-up  📍Office",  # 09:00 UTC shown in local time
            "• 12:00–13:00 Review",
            "• 15:00–15:15 Call",
            "",
            "🟢 Huecos libres (09:00–19:00): 09:00–10:00, 10:20–12:00, 13:00–15:00, 15:15–19:00",
        ]))

    def test_short_gaps_are_not_listed(self):
        items = [event("A", "2026-10-30T09:20:00+01:00", "2026-10-30T18:40:00+01:00")]
        text = digests.agenda(items, NOW, Messages("en"), work_start=(9, 0), work_end=(19, 0))
        self.assertNotIn("Free slots", text)

    def test_custom_working_hours(self):
        items = [event("A", "2026-10-30T10:00:00+01:00", "2026-10-30T11:00:00+01:00")]
        text = digests.agenda(items, NOW, Messages("en"), work_start=(8, 30), work_end=(14, 0))
        self.assertIn("🟢 Free slots (08:30–14:00): 08:30–10:00, 11:00–14:00", text)

    def test_overlapping_and_late_events(self):
        items = [
            event("A", "2026-10-30T09:00:00+01:00", "2026-10-30T12:00:00+01:00"),
            event("B", "2026-10-30T10:00:00+01:00", "2026-10-30T11:00:00+01:00"),
            event("C", "2026-10-30T20:00:00+01:00", "2026-10-30T21:00:00+01:00"),
        ]
        text = digests.agenda(items, NOW, Messages("en"))
        self.assertTrue(text.endswith("🟢 Free slots (09:00–19:00): 12:00–19:00"))

    def test_no_events(self):
        self.assertEqual(digests.agenda([], NOW, Messages("en")),
                         "🗓️ Today's agenda (2026-10-30)\n\nNo events today. Free day. 🎉")

    def test_untitled_event(self):
        items = [{"start": {"dateTime": "2026-10-30T10:00:00+01:00"}, "end": {}}]
        self.assertIn("• 10:00–10:00 (no title)", digests.agenda(items, NOW, Messages("en")))

    def test_calendar_digest_asks_for_today_and_follows_pages(self):
        url = digests.CALENDAR + "team%40example.com/events"
        google = FakeGoogle({url: [
            {"items": [self.ITEMS[0]], "nextPageToken": "page2"},
            {"items": [self.ITEMS[3]]},
        ]})
        text = digests.calendar_digest(google, Messages("en"), "team@example.com", NOW, (9, 0), (19, 0))
        self.assertIn("You have 2 event(s):", text)
        first, second = google.calls
        self.assertEqual(first[1]["timeMin"], "2026-10-30T00:00:00+01:00")
        self.assertEqual(first[1]["timeMax"], "2026-10-31T00:00:00+01:00")
        self.assertEqual(first[1]["singleEvents"], "true")
        self.assertNotIn("pageToken", first[1])
        self.assertEqual(second[1]["pageToken"], "page2")


if __name__ == "__main__":
    unittest.main()
