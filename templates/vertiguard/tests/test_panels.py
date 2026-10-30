import unittest
from datetime import datetime

import fmt
import messages
import panels
from snapshot import PROBES
from tests.fakes import NOW, TZ, context, sample


def data(**changes):
    """Probe results by snapshot name, from the sample, with some of them replaced."""
    raw = sample()
    result = {name: raw[probe] for name, probe in PROBES.items()}
    result.update(changes)
    return result


class FormatTest(unittest.TestCase):
    def tearDown(self):
        messages.set_language("en")

    def test_numbers_and_sizes_follow_the_language(self):
        messages.set_language("es")
        self.assertEqual(fmt.size(1.9 * 1024 ** 3), "1,9 GB")
        self.assertEqual(fmt.number(1234.5, 1), "1.234,5")
        messages.set_language("en")
        self.assertEqual(fmt.size(980 * 1024 ** 2), "980 MB")
        self.assertEqual(fmt.size(512), "512 B")

    def test_bar_and_meter(self):
        self.assertEqual(fmt.bar(0), "▱" * 10)
        self.assertEqual(fmt.bar(24), "▰▰" + "▱" * 8)
        self.assertEqual(fmt.bar(150), "▰" * 10)
        self.assertEqual(fmt.meter("RAM", 24), "<code>RAM   ▰▰▱▱▱▱▱▱▱▱  24%</code>")

    def test_durations_and_days(self):
        self.assertEqual(fmt.duration(781241), "9 d 1 h")
        self.assertEqual(fmt.duration(3 * 3600 + 120), "3 h 2 min")
        messages.set_language("es")
        self.assertEqual(fmt.day(datetime(2026, 10, 29, 23, 10, tzinfo=TZ), NOW), "ayer a las 23:10")
        self.assertEqual(fmt.stamp(NOW), "viernes 30 oct · 09:00")

    def test_parse_time(self):
        self.assertEqual(fmt.parse_time("2026-10-30T03:30:01.971Z", TZ).hour, 4)
        self.assertEqual(fmt.parse_time("2026-10-30T03:30:01.123456789+01:00", TZ).hour, 3)
        self.assertEqual(fmt.parse_time("2026-10-30T15:44:01+0100", TZ).hour, 15)

    def test_html_is_escaped(self):
        self.assertEqual(fmt.esc("<b>&"), "&lt;b&gt;&amp;")


class AssessTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_healthy_server(self):
        self.assertEqual(panels.assess(data(), context()), ([], []))

    def test_problems_and_warnings(self):
        d = data()
        d["services"] = dict(d["services"], checks={"nginx": "FAIL", "https://example.com": "FAIL(503)"})
        d["system"] = dict(d["system"], disks=[{"mount": "/", "size": 1, "used": 1, "pct": 75}])
        d["updates"] = dict(d["updates"], security=2, reboot_required=True)
        d["docker"] = {"error": "docker: permission denied"}
        bad, warn = panels.assess(d, context())
        self.assertEqual(bad, ["<b>nginx</b> is down", "<b>example.com</b> is down"])
        self.assertIn("Disk / at 75%", warn)
        self.assertIn("2 security updates pending", warn)
        self.assertIn("Reboot needed to apply installed updates", warn)
        self.assertIn("Could not read Docker", warn)

    def test_missing_backup_only_counts_after_the_backup_hour(self):
        d = data()
        d["backups"] = dict(d["backups"], files=d["backups"]["files"][:1])
        self.assertEqual(panels.assess(d, context(now=NOW.replace(hour=5)))[0], [])
        self.assertEqual(panels.assess(d, context())[0], ["No backup from today"])

    def test_names_from_the_server_are_escaped(self):
        d = data()
        d["services"] = {"checks": {"<script>": "FAIL"}}
        self.assertEqual(panels.assess(d, context())[0], ["<b>&lt;script&gt;</b> is down"])


class ReportTest(unittest.TestCase):
    def tearDown(self):
        messages.set_language("en")

    def test_healthy_report_in_spanish(self):
        messages.set_language("es")
        text = panels.full(data(), context())
        self.assertIn("🛡 <b>VertiGuard</b> · <b>vps1</b>", text)
        self.assertIn("viernes 30 oct · 09:00", text)
        self.assertIn("🟢 <b>Todo en orden</b>", text)
        self.assertIn("🟢 nginx · 🟢 mariadb", text)
        self.assertIn("<code>138 ms</code>", text)
        self.assertIn("<code>RAM   ▰▰▰▱▱▱▱▱▱▱  25%</code> 2,0 GB de 8,0 GB", text)
        self.assertIn("🚫 2 IPs bloqueadas · 4 baneos nuevos", text)
        self.assertIn("🔑 3 accesos SSH · último: root a las 08:12", text)
        self.assertIn("Copia de hoy a las 04:30 · 17 KB · 2 guardadas", text)
        self.assertIn("2 certificados · el primero caduca en 53 días (intranet.example.com)", text)
        self.assertIn("🟢 app · 129 MB", text)
        self.assertIn("✅ Sistema al día", text)

    def test_unconfigured_and_failed_sections_are_left_out(self):
        text = panels.full(data(backups={"configured": False}, docker={"error": "boom"}), context())
        self.assertNotIn("Backups", text)
        self.assertNotIn("🐳", text)
        self.assertIn("🟡 <b>1 warning</b>", text)


class PanelsTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")

    def test_every_view_renders(self):
        for name, (_, build) in panels.VIEWS.items():
            text = build(data(), context())
            self.assertTrue(text.strip(), name)
            self.assertNotIn("{", text, name)

    def test_views_say_when_something_is_missing(self):
        self.assertIn("Not set up on this server.", panels.backups(data(backups={"configured": False}), context()))
        self.assertIn("Could not read it: sudo failed", panels.services(data(services={"error": "sudo failed"}), context()))

    def test_security_lists_ips_and_logins(self):
        text = panels.security(data(), context())
        self.assertIn("<pre>192.0.2.7\n198.51.100.9</pre>", text)
        self.assertIn("• root · publickey · 08:12 from <code>203.0.113.5</code>", text)

    def test_down_site_shows_the_code(self):
        d = data(services={"checks": {"https://example.com": "FAIL(503)", "https://down.example.com": "FAIL(000)"}})
        text = panels.services(d, context())
        self.assertIn("🔴 <b>example.com</b> · answers 503", text)
        self.assertIn("🔴 <b>down.example.com</b> · does not answer", text)


if __name__ == "__main__":
    unittest.main()
