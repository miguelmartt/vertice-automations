"""Alerts when something changes, and the daily report.

Services (every 5 min), disk/RAM (every hour), certificates and backups (daily) only alert when the
state changes, both ways, and what was last reported is kept on disk so a restart does not repeat
alerts. The daily report goes out every day at REPORT_HOUR with everything in one message.
"""

import fmt
import panels
from fmt import esc
from messages import t
from probes import ProbeError
from scheduler import daily_at, every


class Alerts:
    def __init__(self, telegram, chat_id, state, snapshot, context, resource_pct=80, ssl_days=15, buttons=True):
        self.tg = telegram
        self.chat_id = chat_id
        self.state = state
        self.snapshot = snapshot
        self.context = context  # callable → panels.Context with the current time
        self.resource_pct = resource_pct
        self.ssl_days = ssl_days
        self.buttons = buttons

    def jobs(self, report_hour=9, backup_hour=6):
        """(name, when, job) for the scheduler. The name doubles as the job_<name> message key."""
        jobs = [
            ("services", every(5 * 60), self.services),
            ("resources", every(60 * 60), self.resources),
            ("backups", daily_at(backup_hour), self.backups),
            ("ssl", daily_at(9 if report_hour is None else report_hour), self.ssl),
        ]
        if report_hour is not None:
            jobs.append(("report", daily_at(report_hour), self.report))
        return jobs

    def read(self, name):
        """A fresh probe result; None if the feature is not set up. A failed probe raises."""
        data = self.snapshot.read([name], fresh=True)[name]
        if "error" in data:
            raise ProbeError(data["error"])
        return None if data.get("configured") is False else data

    def send(self, lines, command):
        ctx = self.context()
        footer = t("alert_footer", time=fmt.clock(ctx.now), command=t("cmd_" + command))
        self.tg.send(self.chat_id, "\n".join(lines + ["", f"<i>{footer}</i>"]), html=True)

    def report_changes(self, key, bad, recovered_line, titles, command):
        """bad: {id: line}. Sends what started failing or recovered since the last alert."""
        before = self.state.get(key, [])
        new = [k for k in bad if k not in before]
        back = [k for k in before if k not in bad]
        if not (new or back):
            return
        server = esc(self.context().server)
        lines = []
        if new:
            lines += [t(titles[0], server=server)] + [f"• {bad[k]}" for k in new]
        if back:
            lines += ([""] if lines else []) + [t(titles[1], server=server)] + [f"• {recovered_line(k)}" for k in back]
        self.send(lines, command)
        self.state.set(key, list(bad))

    def services(self):
        s = self.read("services")
        down = {}
        for name, state in s["checks"].items():
            if str(state).startswith("OK"):
                continue
            if "://" in name:
                code = str(state)[5:-1] if str(state).startswith("FAIL(") else ""
                reason = t("site_code", code=esc(code)) if code and code != "000" else t("site_no_answer")
                down[name] = t("alert_site_down", name=esc(fmt.host(name)), reason=reason)
            else:
                down[name] = t("alert_unit_down", name=esc(name))
        self.report_changes("services_down", down, lambda k: t("alert_item_up", name=esc(fmt.host(k))),
                            ("alert_down_title", "alert_up_title"), "services")

    def resources(self):
        system = self.read("system")
        values = {"ram": (t("lbl_ram"), panels.ram_pct(system))}
        for disk in system.get("disks") or []:
            values["disk:" + disk["mount"]] = (f"{t('lbl_disk')} {disk['mount']}", disk["pct"])
        high = {k: t("alert_res_item", label=esc(label), pct=round(pct), limit=self.resource_pct)
                for k, (label, pct) in values.items() if pct >= self.resource_pct}

        def recovered(k):
            label, pct = values.get(k, (k, 0))
            return t("alert_res_ok_item", label=esc(label), pct=round(pct))

        self.report_changes("resources_high", high, recovered, ("alert_res_title", "alert_res_ok_title"), "resources")

    def ssl(self):
        ssl = self.read("ssl")
        days = {c["name"]: c["days"] for c in ssl["certs"]}
        expiring = {n: t("alert_ssl_item", name=esc(n), days=d) for n, d in days.items() if d < self.ssl_days}
        self.report_changes("ssl_expiring", expiring, lambda n: t("alert_ssl_item", name=esc(n), days=days.get(n, "?")),
                            ("alert_ssl_title", "alert_ssl_ok_title"), "ssl")

    def backups(self):
        b = self.read("backups")
        if b is None:
            return
        ctx = self.context()
        summary = panels.backups_summary(b, ctx)
        missing = not summary["today"]
        if missing == self.state.get("backup_missing", False):
            return
        server = esc(ctx.server)
        if missing:
            last = t("alert_bk_missing", when=fmt.day(summary["newest"][0], ctx.now)) if summary["newest"] else t("bk_none")
            lines = [t("alert_bk_missing_title", server=server), last]
        else:
            when, newest = summary["newest"]
            lines = [t("alert_bk_ok_title", server=server), t("alert_bk_ok", time=fmt.clock(when), size=fmt.size(newest["Size"]))]
        self.send(lines, "backups")
        self.state.set("backup_missing", missing)

    def report(self):
        text = panels.full(self.snapshot.read(), self.context())
        extra = {}
        if self.buttons:
            extra["reply_markup"] = {"inline_keyboard": [[{"text": t("btn_refresh"), "callback_data": "r:report"},
                                                          {"text": t("btn_menu"), "callback_data": "m"}]]}
        self.tg.send(self.chat_id, text, html=True, **extra)
