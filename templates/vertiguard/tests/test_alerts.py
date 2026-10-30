import unittest

import messages
from alerts import Alerts
from tests.fakes import FakeProbes, FakeTelegram, MemoryState

TS = "2026-10-30T09:00:00+01:00"


def make(outputs, **kwargs):
    tg, state, probes = FakeTelegram(), MemoryState(), FakeProbes(outputs)
    return Alerts(tg, 42, state, probes, **kwargs), tg, state, probes


class ServicesTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_alerts_only_when_something_changes(self):
        checks = {"nginx": "OK", "https://example.com": "OK"}
        alerts, tg, _, _ = make({"check_services.sh": lambda: {"ts": TS, "checks": dict(checks)}})
        alerts.services()
        self.assertEqual(tg.sent, [])

        checks["nginx"] = "FAIL"
        alerts.services()
        alerts.services()
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("incident", tg.texts[0])
        self.assertIn("• nginx: FAIL", tg.texts[0])
        self.assertTrue(tg.sent[0]["markdown"])

        checks["nginx"] = "OK"
        alerts.services()
        self.assertEqual(len(tg.sent), 2)
        self.assertIn("recovered", tg.texts[1])

    def test_reports_failure_and_recovery_in_one_message(self):
        state_before = ["nginx"]
        alerts, tg, state, _ = make({"check_services.sh": {"ts": TS, "checks": {"nginx": "OK", "mariadb": "FAIL"}}})
        state.set("services_down", state_before)
        alerts.services()
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("incident", tg.texts[0])
        self.assertIn("recovered", tg.texts[0])
        self.assertEqual(state.get("services_down"), ["mariadb"])

    def test_escapes_markdown_in_names(self):
        alerts, tg, _, _ = make({"check_services.sh": {"ts": TS, "checks": {"my_app": "FAIL"}}})
        alerts.services()
        self.assertIn("my\\_app", tg.texts[0])


class ResourcesAndSslTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("es")

    def tearDown(self):
        messages.set_language("en")

    def test_resources_threshold(self):
        alerts, tg, _, _ = make({"disk_ram.sh": {"ts": TS, "disk_pct": 91, "ram_pct": 40}}, resource_pct=90)
        alerts.resources()
        self.assertIn("recursos altos", tg.texts[0])
        self.assertIn("Disco /: 91% (≥90%)", tg.texts[0])
        self.assertNotIn("RAM", tg.texts[0])

    def test_ssl_expiring(self):
        alerts, tg, state, _ = make({"ssl_check.sh": {"ts": TS, "certs": [
            {"name": "example.com", "days": 10}, {"name": "other.example.com", "days": 80}]}})
        alerts.ssl()
        self.assertIn("example.com: 10 días", tg.texts[0])
        self.assertEqual(state.get("ssl_expiring"), ["example.com"])


class BackupsTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_not_configured_is_silent(self):
        alerts, tg, _, _ = make({"backup_watchdog.sh": {"ts": TS, "configured": False}})
        alerts.backups()
        self.assertEqual(tg.sent, [])

    def test_missing_then_back(self):
        result = {"ts": TS, "configured": True, "today": "2026-10-30", "today_count": 0, "newest": "backup-2026-10-29.tar"}
        alerts, tg, _, _ = make({"backup_watchdog.sh": lambda: dict(result)})
        alerts.backups()
        alerts.backups()
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("NOT found", tg.texts[0])
        result["today_count"] = 1
        alerts.backups()
        self.assertIn("backup OK", tg.texts[1])


class ReportsTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_fail2ban_report_always_sent(self):
        report = {"ts": TS, "configured": True, "jail": "sshd", "cur_banned": 2, "tot_banned": 9,
                  "cur_failed": 1, "tot_failed": 30, "banned_ips": "192.0.2.1 192.0.2.2"}
        alerts, tg, _, _ = make({"fail2ban_report.sh": report})
        alerts.fail2ban()
        alerts.fail2ban()
        self.assertEqual(len(tg.sent), 2)
        self.assertIn("Banned now: 2 (total: 9)", tg.texts[0])
        self.assertIn("192.0.2.1 192.0.2.2", tg.texts[0])

    def test_updates(self):
        alerts, tg, _, probes = make({"updates_check.sh": {"ts": TS, "configured": True, "manager": "apt", "updates": 3}})
        alerts.updates()
        self.assertIn("3 packages", tg.texts[0])
        self.assertIn("apt list --upgradable", tg.texts[0])

    def test_every_job_has_a_message_name(self):
        alerts, _, _, _ = make({})
        for language in messages.TEXTS:
            for name, _, _ in alerts.jobs():
                self.assertIn("job_" + name, messages.TEXTS[language])


if __name__ == "__main__":
    unittest.main()
