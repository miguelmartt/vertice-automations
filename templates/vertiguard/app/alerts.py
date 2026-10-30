"""Scheduled checks: services, disk/RAM, SSL, backups, fail2ban and pending updates.

Services, disk/RAM, SSL and backups only alert when something changes (fails or recovers); what was
last reported is kept on disk so a restart does not repeat alerts. fail2ban and updates send their
report every time.
"""

from messages import t
from scheduler import daily_at, every
from telegram import md

UPDATE_COMMANDS = {"dnf": "dnf check-update", "apt": "apt list --upgradable"}


class Alerts:
    def __init__(self, telegram, chat_id, state, probes, resource_pct=80, ssl_days=15):
        self.tg = telegram
        self.chat_id = chat_id
        self.state = state
        self.probes = probes
        self.resource_pct = resource_pct
        self.ssl_days = ssl_days

    def jobs(self, report_hour=9, backup_hour=6):
        """(name, when, job) for the scheduler. The name doubles as the job_<name> message key."""
        return [
            ("services", every(5 * 60), self.services),
            ("resources", every(60 * 60), self.resources),
            ("backups", daily_at(backup_hour), self.backups),
            ("ssl", daily_at(report_hour), self.ssl),
            ("fail2ban", daily_at(report_hour), self.fail2ban),
            ("updates", daily_at(report_hour, weekday=0), self.updates),
        ]

    def send(self, lines, ts):
        self.tg.send(self.chat_id, "\n".join(lines + ["", "🕒 " + md(ts)]), markdown=True)

    def report_changes(self, key, bad, ts, titles, line):
        """Reports only what started failing or recovered since the last alert."""
        before = self.state.get(key, [])
        new = [k for k in bad if k not in before]
        recovered = [k for k in before if k not in bad]
        if not (new or recovered):
            return
        lines = []
        if new:
            lines += [t(titles[0])] + [line(k, True) for k in new]
        if recovered:
            lines += ([""] if lines else []) + [t(titles[1])] + [line(k, False) for k in recovered]
        self.send(lines, ts)
        self.state.set(key, bad)

    def services(self):
        d = self.probes.run("check_services.sh")
        checks = d["checks"]
        self.report_changes(
            "services_down", [k for k, v in checks.items() if not str(v).startswith("OK")], d["ts"],
            ("incident", "recovered"),
            lambda k, bad: f"• {md(k)}: {md(checks[k]) if bad else 'OK'}",
        )

    def resources(self):
        d = self.probes.run("disk_ram.sh")
        pct = {"disk": d["disk_pct"], "ram": d["ram_pct"]}
        self.report_changes(
            "resources_high", [k for k, v in pct.items() if v >= self.resource_pct], d["ts"],
            ("resources_high", "resources_ok"),
            lambda k, bad: f"• {t('label_' + k)}: {pct[k]}%" + (f" (≥{self.resource_pct}%)" if bad else ""),
        )

    def ssl(self):
        d = self.probes.run("ssl_check.sh")
        days = {c["name"]: c["days"] for c in d["certs"]}
        self.report_changes(
            "ssl_expiring", [n for n, v in days.items() if v < self.ssl_days], d["ts"],
            ("ssl_expiring", "ssl_renewed"),
            lambda n, bad: t("ssl_line", name=md(n), days=days.get(n, "?")),
        )

    def backups(self):
        d = self.probes.run("backup_watchdog.sh")
        if not d.get("configured"):
            return
        missing = not d["today_count"]
        if missing == self.state.get("backup_missing", False):
            return
        title = "backup_missing" if missing else "backup_ok"
        self.send([t(title, today=md(d["today"])), t("backup_newest", name=md(d["newest"] or "—"))], d["ts"])
        self.state.set("backup_missing", missing)

    def fail2ban(self):
        d = self.probes.run("fail2ban_report.sh")
        if not d.get("configured"):
            return
        lines = [
            t("f2b_title", jail=md(d["jail"])),
            t("f2b_banned", cur=d["cur_banned"], tot=d["tot_banned"]),
            t("f2b_failed", cur=d["cur_failed"], tot=d["tot_failed"]),
        ]
        if d["banned_ips"].strip():
            lines.append(t("f2b_ips", ips=md(d["banned_ips"].strip())))
        self.send(lines, d["ts"])

    def updates(self):
        d = self.probes.run("updates_check.sh", timeout=600)
        if not d.get("configured"):
            return
        if d["updates"]:
            text = t("updates_pending", n=d["updates"], command=UPDATE_COMMANDS.get(d["manager"], d["manager"]))
        else:
            text = t("updates_none")
        self.send([text], d["ts"])
