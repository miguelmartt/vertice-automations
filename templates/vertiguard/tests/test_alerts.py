import unittest

import messages
from alerts import Alerts
from probes import ProbeError
from snapshot import Snapshot
from tests.fakes import FakeProbes, FakeTelegram, MemoryState, context, sample


def make(**outputs):
    probes = sample()
    probes.update(outputs)
    tg, state = FakeTelegram(), MemoryState()
    return Alerts(tg, 42, state, Snapshot(FakeProbes(probes)), context, resource_pct=80, ssl_days=15), tg, state


class ServicesTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_alerts_only_when_something_changes(self):
        checks = {"nginx": "OK", "https://example.com": "OK"}
        alerts, tg, _ = make(**{"check_services.sh": lambda: {"ts": "t", "checks": dict(checks)}})
        alerts.services()
        self.assertEqual(tg.sent, [])

        checks["nginx"] = "FAIL"
        checks["https://example.com"] = "FAIL(503)"
        alerts.services()
        alerts.services()
        self.assertEqual(len(tg.sent), 1)
        text = tg.texts[0]
        self.assertTrue(tg.sent[0]["html"])
        self.assertIn("🔴 <b>vps1: something is down</b>", text)
        self.assertIn("• <b>nginx</b> is not running", text)
        self.assertIn("• <b>example.com</b> answers 503", text)
        self.assertIn("/services for the details", text)

        checks["nginx"] = "OK"
        alerts.services()
        self.assertEqual(len(tg.sent), 2)
        self.assertIn("🟢 <b>vps1: working again</b>\n• <b>nginx</b> is back", tg.texts[1])

    def test_a_failing_probe_raises_for_the_scheduler(self):
        alerts, _, _ = make(**{"check_services.sh": ProbeError("sudo: a password is required")})
        with self.assertRaises(ProbeError):
            alerts.services()


class ResourcesAndSslTest(unittest.TestCase):
    def tearDown(self):
        messages.set_language("en")

    def test_disk_over_the_limit(self):
        messages.set_language("es")
        system = dict(sample()["system.sh"], disks=[{"mount": "/", "size": 1, "used": 1, "pct": 91}])
        alerts, tg, state = make(**{"system.sh": system})
        alerts.resources()
        self.assertIn("🟠 <b>vps1: recursos altos</b>", tg.texts[0])
        self.assertIn("• Disco /: 91 % (umbral 80 %)", tg.texts[0])
        self.assertEqual(state.get("resources_high"), ["disk:/"])

    def test_certificate_about_to_expire(self):
        alerts, tg, _ = make(**{"ssl_check.sh": {"ts": "t", "certs": [{"name": "example.com", "days": 10}]}})
        alerts.ssl()
        self.assertIn("<b>example.com</b>: 10 days left", tg.texts[0])


class BackupsTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_not_configured_is_silent(self):
        alerts, tg, _ = make(**{"backup_watchdog.sh": {"ts": "t", "configured": False}})
        alerts.backups()
        self.assertEqual(tg.sent, [])

    def test_missing_then_back(self):
        backups = dict(sample()["backup_watchdog.sh"])
        today = backups["files"]
        backups["files"] = today[:1]
        alerts, tg, _ = make(**{"backup_watchdog.sh": lambda: dict(backups)})
        alerts.backups()
        alerts.backups()
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("no backup from today", tg.texts[0])
        self.assertIn("The last one is from yesterday at 04:30.", tg.texts[0])
        backups["files"] = today
        alerts.backups()
        self.assertIn("today's backup is there", tg.texts[1])
        self.assertIn("04:30 · 17 KB", tg.texts[1])


class ReportTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_daily_report_with_buttons(self):
        alerts, tg, _ = make()
        alerts.report()
        self.assertIn("🟢 <b>All good</b>", tg.texts[0])
        buttons = [b["callback_data"] for row in tg.sent[0]["reply_markup"]["inline_keyboard"] for b in row]
        self.assertEqual(buttons, ["r:report", "m"])

    def test_report_without_buttons_when_commands_are_off(self):
        alerts, tg, _ = make()
        alerts.buttons = False
        alerts.report()
        self.assertNotIn("reply_markup", tg.sent[0])

    def test_jobs_have_message_names(self):
        alerts, _, _ = make()
        names = [name for name, _, _ in alerts.jobs(report_hour=9)]
        self.assertEqual(names, ["services", "resources", "backups", "ssl", "report"])
        self.assertNotIn("report", [name for name, _, _ in alerts.jobs(report_hour=None)])
        for language in messages.TEXTS:
            for name in names:
                self.assertIn("job_" + name, messages.TEXTS[language])


if __name__ == "__main__":
    unittest.main()
