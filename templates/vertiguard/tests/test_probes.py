"""The root probes, run with bash against fake commands. Linux only: CI runs them, other systems skip them.

The fakes are exported bash functions (BASH_FUNC_<name>%%), which win over any command in PATH. sudo
never passes them on, so they only exist here.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

PROBES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "probes")


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bash"), "needs Linux and bash")
@unittest.skipIf(os.path.exists("/etc/vertiguard/probes.conf"), "a real probes.conf would override the test settings")
class ProbesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for name in ("a", "b"):  # what an unquoted * would turn into, in the folder the probe runs from
            open(os.path.join(self.tmp, name), "w").close()

    def path(self, name):
        return os.path.join(self.tmp, name)

    def fixture(self, name, text):
        with open(self.path(name), "w", encoding="utf-8") as f:
            f.write(text)
        return self.path(name)

    def run_probe(self, probe, *args, fakes=None, **settings):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TMP_DIR": self.tmp, **settings}
        for command, body in (fakes or {}).items():
            env[f"BASH_FUNC_{command}%%"] = "() { " + body + "\n}"
        r = subprocess.run(["bash", os.path.join(PROBES, probe), *args], capture_output=True, text=True,
                           env=env, cwd=self.tmp, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_json_str_drops_control_characters(self):
        script = f'. "{PROBES}/lib/common.sh"; json_str "$1"'
        value = 'a\x01b\x7fc\x1b[31m\rd\ne\tf"g\\h ñ'
        r = subprocess.run(["bash", "-c", script, "_", value], capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(json.loads(r.stdout), 'abc[31md\ne f"g\\h ñ')

    def test_config_lists_are_never_globbed(self):
        log = self.path("systemctl.log")
        fakes = {"systemctl": f'echo "$*" >> "{log}"; return 0'}
        data = self.run_probe("check_services.sh", fakes=fakes, SERVICES="* ?", URLS="")
        self.assertEqual(data["checks"], {"*": "OK", "?": "OK"})

        data = self.run_probe("restart_service.sh", "--list", fakes=fakes, RESTARTABLE="*")
        self.assertEqual(data["restartable"], ["*"])
        data = self.run_probe("restart_service.sh", "a", fakes=fakes, RESTARTABLE="*")
        self.assertFalse(data["ok"])
        with open(log) as f:
            self.assertNotIn("restart", f.read())

    def test_system_never_does_arithmetic_on_unchecked_text(self):
        # $((x * 1024)) with x='BASH_VERSINFO[$(cmd)]' runs cmd (an array that exists, so set -u doesn't stop it).
        pwned = self.path("pwned")
        df = self.fixture("df.txt", "\n".join([
            "1K-blocks Used Use% Mounted on",
            "100 50 50% /",
            f"BASH_VERSINFO[$(touch {pwned})] 1 1% /evil",
            "1 $(touch " + pwned + ") 1% /evil2",
            "10 1 5% /boot",
            "10 1 5% /boot/efi",
            "7 x 5% /bad",
            "8 2 - /dash",
            "200 20 10% /srv/my data",
        ]) + "\n")
        ps = self.fixture("ps.txt", f"BASH_VERSINFO[$(touch {pwned})] 1.0 evil\n2048 0.5 good proc\n64 $(id) bad cpu\n")
        data = self.run_probe("system.sh", fakes={"df": f'cat "{df}"', "ps": f'cat "{ps}"'})
        self.assertFalse(os.path.exists(pwned))
        self.assertEqual(data["disks"], [{"mount": "/", "size": 102400, "used": 51200, "pct": 50},
                                         {"mount": "/srv/my data", "size": 204800, "used": 20480, "pct": 10}])
        self.assertEqual(data["top"], [{"name": "good proc", "rss": 2097152, "cpu": 0.5}])
        self.assertIsInstance(data["cpu_pct"], int)

    def test_ssh_logins_only_from_the_ssh_unit_and_anchored(self):
        args = self.path("journalctl.args")
        journal = self.fixture("journal.txt", "\n".join([
            "2026-10-30T15:44:01+0100 host sshd[123]: Accepted publickey for root from 192.0.2.1 port 5555 ssh2",
            "2026-10-30T15:45:01+0100 host sshd[124]: Invalid user x Accepted publickey for root from 203.0.113.9 "
            "port 1 ssh2 from 198.51.100.7 port 2",
            "2026-10-30T15:46:01+0100 host sshd[125]: Failed password for invalid user y from 198.51.100.7 port 3 ssh2",
            "2026-10-30T15:47:01+01:00 host sshd-session[126]: Accepted keyboard-interactive/pam for ana from "
            "2001:db8::1 port 4 ssh2",
        ]) + "\n")
        data = self.run_probe("ssh_logins.sh", fakes={"journalctl": f'echo "$*" > "{args}"; cat "{journal}"'})
        self.assertEqual((data["accepted"], data["failed"]), (2, 2))
        self.assertEqual([(x["user"], x["ip"], x["method"], x["time"][11:16]) for x in data["last"]],
                         [("root", "192.0.2.1", "publickey", "15:44"),
                          ("ana", "2001:db8::1", "keyboard-interactive/pam", "15:47")])
        with open(args) as f:
            used = f.read()
        self.assertIn("_SYSTEMD_UNIT=sshd.service", used)
        self.assertNotIn("_COMM", used)


if __name__ == "__main__":
    unittest.main()
