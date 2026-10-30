"""What the bot shows: the daily report and one panel per section, as Telegram HTML.

Every function takes the probe results ({name: JSON}, see snapshot.PROBES) and a Context and returns
text. They do no I/O, so they are easy to test.
"""

from datetime import timedelta

import fmt
from fmt import esc, light
from messages import plural, t


class Context:
    def __init__(self, server, now, resource_pct=80, ssl_days=15, backup_hour=6):
        self.server = server
        self.now = now
        self.tz = now.tzinfo
        self.resource_pct = resource_pct
        self.ssl_days = ssl_days
        self.backup_hour = backup_hour


def usable(data, name):
    """The probe result if it ran and its feature is set up, otherwise None."""
    d = data.get(name) or {}
    if not d or "error" in d or d.get("configured") is False:
        return None
    return d


def ram_pct(system):
    total = system["mem_total"] or 1
    return 100 * (total - system["mem_available"]) / total


def root_disk(system):
    disks = system.get("disks") or []
    return next((d for d in disks if d["mount"] == "/"), disks[0] if disks else None)


def ssl_state(days, ctx):
    if days < ctx.ssl_days:
        return "bad"
    return "warn" if days < 2 * ctx.ssl_days else "ok"


def backups_summary(b, ctx):
    files = []
    for f in b.get("files") or []:
        try:
            files.append((fmt.parse_time(f["ModTime"], ctx.tz), f))
        except (KeyError, ValueError):
            continue
    files.sort(key=lambda item: item[0])
    today = [f for _, f in files if f["Name"].startswith(b.get("prefix", "") + b["today"])]
    return {"today": bool(today), "count": len(files), "newest": files[-1] if files else None,
            "recent": files[-5:][::-1]}


def assess(data, ctx):
    """(problems, warnings): one short line each, already HTML-escaped."""
    bad, warn = [], []
    s = usable(data, "services")
    if s:
        for name, state in s["checks"].items():
            if not str(state).startswith("OK"):
                bad.append(t("issue_down", name=esc(fmt.host(name))))
    system = usable(data, "system")
    if system:
        for disk in system.get("disks") or []:
            state = fmt.level(disk["pct"], ctx.resource_pct)
            if state != "ok":
                (bad if state == "bad" else warn).append(t("issue_disk", mount=esc(disk["mount"]), pct=disk["pct"]))
        state = fmt.level(ram_pct(system), ctx.resource_pct)
        if state != "ok":
            (bad if state == "bad" else warn).append(t("issue_ram", pct=round(ram_pct(system))))
        if system["load"][0] > system["cores"]:
            warn.append(t("warn_load", load=fmt.number(system["load"][0], 2), cores=system["cores"]))
    ssl = usable(data, "ssl")
    if ssl:
        for cert in ssl["certs"]:
            if cert["days"] < ctx.ssl_days:
                bad.append(t("issue_ssl", name=esc(cert["name"]), days=cert["days"]))
    b = usable(data, "backups")
    if b and not backups_summary(b, ctx)["today"] and ctx.now.hour >= ctx.backup_hour:
        bad.append(t("issue_backup"))
    u = usable(data, "updates")
    if u:
        if u["security"]:
            warn.append(plural("warn_security", u["security"]))
        if u.get("reboot_required"):
            warn.append(t("warn_reboot"))
    docker = usable(data, "docker")
    if docker:
        for c in docker.get("containers") or []:
            if c.get("State") != "running":
                warn.append(t("warn_container", name=esc(c.get("Names", "?"))))
    for name, d in data.items():
        if isinstance(d, dict) and "error" in d:
            warn.append(t("warn_probe", what=t("name_" + name)))
    return bad, warn


# ── Lines shared by the report and the panels ─────────────────────────────────────────────────────

def service_lines(s, detailed=False):
    units, sites = [], []
    for name, state in s["checks"].items():
        ok = str(state).startswith("OK")
        if "://" not in name:
            if detailed:
                units.append(f"{light('ok' if ok else 'bad')} <b>{esc(name)}</b> · {t('running' if ok else 'stopped')}")
            else:
                units.append(f"{light('ok' if ok else 'bad')} {esc(name)}")
            continue
        ms = (s.get("ms") or {}).get(name)
        if ok:
            state_ = "warn" if ms and ms > 2000 else "ok"
            speed = f" <code>{fmt.number(ms)} ms</code>" if ms is not None else ""
            sites.append(f"{light(state_)} <b>{esc(fmt.host(name))}</b>{speed}")
        else:
            code = str(state)[5:-1] if str(state).startswith("FAIL(") else ""
            reason = t("site_code", code=esc(code)) if code and code != "000" else t("site_no_answer")
            sites.append(f"{light('bad')} <b>{esc(fmt.host(name))}</b> · {reason}")
    if detailed:
        return units + sites
    return ([" · ".join(units)] if units else []) + sites


def resource_lines(system, ctx):
    ram = ram_pct(system)
    lines = [
        fmt.meter(t("lbl_cpu"), system["cpu_pct"]),
        fmt.meter(t("lbl_ram"), ram) + " " + t("of", used=fmt.size(system["mem_total"] - system["mem_available"]),
                                                total=fmt.size(system["mem_total"])),
    ]
    disk = root_disk(system)
    if disk:
        lines.append(fmt.meter(t("lbl_disk"), disk["pct"]) + " " + t("of", used=fmt.size(disk["used"]),
                                                                       total=fmt.size(disk["size"])))
    lines.append(t("load_line", load=fmt.number(system["load"][0], 2), cores=system["cores"],
                   uptime=fmt.duration(system["uptime_s"])))
    return lines


def security_lines(f2b, ssh, ctx):
    lines = []
    if f2b:
        lines.append(t("sec_banned", now=f2b["cur_banned"], new=f2b.get("bans_24h", 0)))
    if ssh:
        lines.append(plural("sec_failed", ssh["failed"]))
        last = ssh["last"][-1] if ssh.get("last") else None
        if last:
            lines.append(t("sec_logins", n=ssh["accepted"], user=esc(last["user"]), time=esc(last["time"][11:16])))
        else:
            lines.append(t("sec_no_logins"))
    return lines


def backup_lines(b, ctx):
    s = backups_summary(b, ctx)
    if not s["newest"]:
        return [f"{light('bad')} {t('bk_none')}"]
    when, newest = s["newest"]
    if s["today"]:
        return [f"{light('ok')} " + t("bk_today", time=fmt.clock(when), size=fmt.size(newest["Size"]), count=s["count"])]
    state = "bad" if ctx.now.hour >= ctx.backup_hour else "warn"
    return [f"{light(state)} " + t("bk_missing", when=fmt.day(when, ctx.now))]


def ssl_lines(ssl, ctx):
    certs = sorted(ssl["certs"], key=lambda c: c["days"])
    if not certs:
        return [t("ssl_none")]
    first = certs[0]
    return [f"{light(ssl_state(first['days'], ctx))} " + plural("ssl_summary", len(certs), days=first["days"],
                                                                 name=esc(first["name"]))]


def docker_stats(docker):
    return {s.get("Name"): s for s in docker.get("stats") or []}


DOCKER_UNITS = {"b": 1, "kb": 1000, "kib": 1024, "mb": 1000 ** 2, "mib": 1024 ** 2, "gb": 1000 ** 3, "gib": 1024 ** 3}


def docker_mem(stat):
    """«128.6MiB / 7.69GiB» → «129 MB», in the same format as the rest; the raw text if it can't be read."""
    used = (stat or {}).get("MemUsage", "").split(" / ")[0].strip()
    number = used.rstrip("BbKkMmGgIi")
    unit = used[len(number):].lower()
    try:
        return fmt.size(float(number) * DOCKER_UNITS[unit])
    except (ValueError, KeyError):
        return esc(used)


def docker_lines(docker):
    stats = docker_stats(docker)
    lines = []
    for c in (docker.get("containers") or [])[:5]:
        running = c.get("State") == "running"
        extra = docker_mem(stats.get(c.get("Names"))) if running else t("stopped")
        lines.append(f"{light('ok' if running else 'bad')} {esc(c.get('Names', '?'))} · {extra}")
    return lines or [t("docker_none")]


def update_lines(u):
    lines = []
    if u["updates"]:
        lines.append(f"{light('warn' if u['security'] else 'ok')} " + plural("upd_pending", u["updates"], security=u["security"]))
    else:
        lines.append(t("upd_none"))
    if u.get("reboot_required"):
        lines.append(t("upd_reboot"))
    return lines


# ── Daily report ──────────────────────────────────────────────────────────────────────────────────

def full(data, ctx):
    bad, warn = assess(data, ctx)
    out = [f"🛡 <b>VertiGuard</b> · <b>{esc(ctx.server)}</b>", f"<i>{fmt.stamp(ctx.now)}</i>", ""]
    if bad:
        out.append(f"{light('bad')} <b>{plural('status_bad', len(bad))}</b>")
    elif warn:
        out.append(f"{light('warn')} <b>{plural('status_warn', len(warn))}</b>")
    else:
        out.append(f"{light('ok')} <b>{t('status_ok')}</b>")
    out += [f"• {line}" for line in bad + warn]

    sections = []
    s = usable(data, "services")
    if s:
        sections.append(("title_services", service_lines(s)))
    system = usable(data, "system")
    if system:
        sections.append(("title_resources", resource_lines(system, ctx)))
    f2b, ssh = usable(data, "fail2ban"), usable(data, "ssh")
    if f2b or ssh:
        sections.append(("title_security_24h", security_lines(f2b, ssh, ctx)))
    b = usable(data, "backups")
    if b:
        sections.append(("title_backups", backup_lines(b, ctx)))
    ssl = usable(data, "ssl")
    if ssl:
        sections.append(("title_ssl", ssl_lines(ssl, ctx)))
    docker = usable(data, "docker")
    if docker:
        sections.append(("title_docker", docker_lines(docker)))
    u = usable(data, "updates")
    if u:
        sections.append(("title_updates", update_lines(u)))
    for title, lines in sections:
        out += ["", f"<b>{t(title)}</b>"] + lines
    out += ["", f"<i>{t('report_footer')}</i>"]
    return "\n".join(out)


# ── Detailed panels (one per command) ─────────────────────────────────────────────────────────────

def frame(title, lines, ctx):
    return "\n".join([f"<b>{t(title)}</b> · {esc(ctx.server)}", ""] + lines + ["", f"<i>🕒 {fmt.clock(ctx.now)}</i>"])


def unavailable(data, name):
    d = data.get(name) or {}
    if "error" in d:
        return [t("probe_failed", error=esc(d["error"]))]
    return [t("not_configured")]


def services(data, ctx):
    s = usable(data, "services")
    return frame("title_services", service_lines(s, detailed=True) if s else unavailable(data, "services"), ctx)


def resources(data, ctx):
    system = usable(data, "system")
    if not system:
        return frame("title_resources", unavailable(data, "system"), ctx)
    lines = [fmt.meter(t("lbl_cpu"), system["cpu_pct"]),
             fmt.meter(t("lbl_ram"), ram_pct(system)) + " " + t("of", used=fmt.size(system["mem_total"] - system["mem_available"]),
                                                                total=fmt.size(system["mem_total"]))]
    if system["swap_total"]:
        swap = 100 * (system["swap_total"] - system["swap_free"]) / system["swap_total"]
        lines.append(fmt.meter(t("lbl_swap"), swap) + " " + t("of", used=fmt.size(system["swap_total"] - system["swap_free"]),
                                                               total=fmt.size(system["swap_total"])))
    for disk in system.get("disks") or []:
        lines.append(fmt.meter(t("lbl_disk"), disk["pct"]) + f" {esc(disk['mount'])} · "
                     + t("of", used=fmt.size(disk["used"]), total=fmt.size(disk["size"])))
    load = " · ".join(fmt.number(x, 2) for x in system["load"])
    lines += ["", t("load_detail", load=load, cores=system["cores"]),
              t("uptime_detail", uptime=fmt.duration(system["uptime_s"]), os=esc(system.get("os") or "Linux"),
                kernel=esc(system.get("kernel", "")))]
    if system.get("top"):
        lines += ["", f"<b>{t('top_title')}</b>"]
        lines += [f"<code>{esc(p['name'][:18]).ljust(18)} {fmt.size(p['rss']).rjust(8)}</code>" for p in system["top"]]
    return frame("title_resources", lines, ctx)


def security(data, ctx):
    f2b, ssh = usable(data, "fail2ban"), usable(data, "ssh")
    lines = []
    if f2b:
        lines += [t("f2b_now", n=f2b["cur_banned"], jail=esc(f2b["jail"])),
                  t("f2b_24h", n=f2b.get("bans_24h", 0)),
                  t("f2b_total", n=f2b["tot_banned"])]
    if ssh:
        lines += ["", t("ssh_accepted", n=ssh["accepted"]), plural("sec_failed", ssh["failed"])]
        if ssh.get("last"):
            lines += ["", f"<b>{t('ssh_last_title')}</b>"]
            lines += [t("ssh_last_item", user=esc(x["user"]), method=esc(x["method"]), time=esc(x["time"][11:16]),
                        ip=esc(x["ip"])) for x in reversed(ssh["last"])]
    if f2b and f2b["banned_ips"].strip():
        ips = f2b["banned_ips"].split()
        lines += ["", f"<b>{t('banned_title', n=len(ips))}</b>", "<pre>" + esc("\n".join(ips[:15])) + "</pre>"]
        if len(ips) > 15:
            lines.append(t("and_more", n=len(ips) - 15))
    if not lines:
        lines = unavailable(data, "fail2ban")
    return frame("title_security", lines, ctx)


def backups(data, ctx):
    b = usable(data, "backups")
    if not b:
        return frame("title_backups", unavailable(data, "backups"), ctx)
    s = backups_summary(b, ctx)
    lines = backup_lines(b, ctx)
    if s["recent"]:
        lines += ["", f"<b>{t('bk_recent_title', n=s['count'])}</b>"]
        lines += [f"• {fmt.day(when, ctx.now)} · {fmt.size(f['Size'])}" for when, f in s["recent"]]
    return frame("title_backups", lines, ctx)


def ssl(data, ctx):
    s = usable(data, "ssl")
    if not s:
        return frame("title_ssl", unavailable(data, "ssl"), ctx)
    lines = []
    for cert in sorted(s["certs"], key=lambda c: c["days"]):
        expires = ctx.now + timedelta(days=cert["days"])
        lines.append(f"{light(ssl_state(cert['days'], ctx))} <b>{esc(cert['name'])}</b>")
        lines.append("    " + t("ssl_item", days=cert["days"], day=expires.day,
                                 month=t("months").split(",")[expires.month - 1]))
    return frame("title_ssl", lines or [t("ssl_none")], ctx)


def docker(data, ctx):
    d = usable(data, "docker")
    if not d:
        return frame("title_docker", unavailable(data, "docker"), ctx)
    stats = docker_stats(d)
    lines = []
    for c in d.get("containers") or []:
        running = c.get("State") == "running"
        state = t("running") if running else f"{t('stopped')} ({esc(c.get('Status', ''))})"
        lines.append(f"{light('ok' if running else 'bad')} <b>{esc(c.get('Names', '?'))}</b> · {state}")
        s = stats.get(c.get("Names")) or {}
        if running and s:
            lines.append("    " + t("docker_usage", cpu=esc(s.get("CPUPerc", "?")), mem=docker_mem(s)))
        lines.append(f"    <code>{esc(c.get('Image', ''))}</code>")
    return frame("title_docker", lines or [t("docker_none")], ctx)


def updates(data, ctx):
    u = usable(data, "updates")
    if not u:
        return frame("title_updates", unavailable(data, "updates"), ctx)
    lines = update_lines(u)
    if u.get("packages"):
        lines += ["", "<pre>" + esc("\n".join(u["packages"])) + "</pre>"]
        lines.append(t("upd_how", command=esc("dnf upgrade" if u["manager"] == "dnf" else "apt upgrade")))
    return frame("title_updates", lines, ctx)


VIEWS = {
    "report": (None, full),
    "services": (["services"], services),
    "resources": (["system"], resources),
    "security": (["fail2ban", "ssh"], security),
    "backups": (["backups"], backups),
    "ssl": (["ssl"], ssl),
    "docker": (["docker"], docker),
    "updates": (["updates"], updates),
}
