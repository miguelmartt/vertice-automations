"""Test doubles and sample probe output: no network, sudo or disk."""

from datetime import datetime
from zoneinfo import ZoneInfo

from panels import Context

TZ = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=TZ)


def context(now=NOW, **kwargs):
    return Context("vps1", now, **kwargs)


class FakeTelegram:
    def __init__(self):
        self.sent = []
        self.edits = []
        self.calls = []

    def send(self, chat_id, text, markdown=False, html=False, **extra):
        self.sent.append({"chat_id": chat_id, "text": text, "html": html, **extra})

    def send_long(self, chat_id, text, **extra):
        self.send(chat_id, text, **extra)

    def edit(self, chat_id, message_id, text, html=False, **extra):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text, "html": html, **extra})

    def call(self, method, params=None, timeout=30):
        self.calls.append((method, params))
        return True

    @property
    def texts(self):
        return [m["text"] for m in self.sent]


class FakeProbes:
    """outputs maps a probe name to its JSON (a dict), a function of its arguments, or an exception."""

    def __init__(self, outputs):
        self.outputs = outputs
        self.ran = []

    def run(self, name, *args, timeout=180):
        self.ran.append((name,) + args)
        out = self.outputs[name]
        if isinstance(out, Exception):
            raise out
        return out(*args) if callable(out) else dict(out)


class MemoryState:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def sample():
    """What the probes print on a healthy server (trimmed from a real one)."""
    return {
        "check_services.sh": {"ts": "2026-10-30T09:00:00+01:00", "checks": {"nginx": "OK", "mariadb": "OK",
                                                                            "https://example.com": "OK"},
                              "ms": {"https://example.com": 138}},
        "system.sh": {"ts": "t", "host": "vps1", "os": "AlmaLinux 9.8", "kernel": "5.14.0", "uptime_s": 781241,
                      "cpu_pct": 3, "cores": 6, "load": [0.09, 0.05, 0.01], "mem_total": 8 * 1024 ** 3,
                      "mem_available": 6 * 1024 ** 3, "swap_total": 2 * 1024 ** 3, "swap_free": 2 * 1024 ** 3,
                      "disks": [{"mount": "/", "size": 239 * 1024 ** 3, "used": 10 * 1024 ** 3, "pct": 5}],
                      "top": [{"name": "mariadbd", "rss": 151 * 1024 ** 2, "cpu": 0.4}]},
        "ssl_check.sh": {"ts": "t", "certs": [{"name": "example.com", "days": 85}, {"name": "intranet.example.com", "days": 53}]},
        "fail2ban_report.sh": {"ts": "t", "configured": True, "jail": "sshd", "cur_failed": 2, "tot_failed": 2988,
                               "cur_banned": 2, "tot_banned": 156, "bans_24h": 4, "banned_ips": "192.0.2.7 198.51.100.9"},
        "ssh_logins.sh": {"ts": "t", "accepted": 3, "failed": 565,
                          "last": [{"time": "2026-10-30T08:12:01+0100", "user": "root", "ip": "203.0.113.5",
                                    "method": "publickey"}]},
        "backup_watchdog.sh": {"ts": "t", "configured": True, "today": "2026-10-30", "prefix": "backup-",
                               "files": [{"Name": "backup-2026-10-29_0430.tar.gz.enc", "Size": 16016,
                                          "ModTime": "2026-10-29T03:30:01.156Z"},
                                         {"Name": "backup-2026-10-30_0430.tar.gz.enc", "Size": 17744,
                                          "ModTime": "2026-10-30T03:30:01.971Z"}]},
        "docker_status.sh": {"ts": "t", "configured": True,
                             "containers": [{"Names": "app", "State": "running", "Status": "Up 9 days", "Image": "app:latest"}],
                             "stats": [{"Name": "app", "CPUPerc": "0.05%", "MemUsage": "128.6MiB / 7.69GiB"}]},
        "updates_check.sh": {"ts": "t", "configured": True, "manager": "dnf", "updates": 0, "security": 0,
                             "reboot_required": False, "packages": []},
        "restart_service.sh": lambda *a: {"restartable": ["nginx", "mariadb"]} if a == ("--list",)
        else {"ok": True, "state": "active", "service": a[0]},
        "unban_ip.sh": lambda ip: {"ok": True, "ip": ip},
    }
