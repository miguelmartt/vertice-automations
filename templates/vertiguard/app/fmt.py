"""Formatting for the Telegram messages: HTML escaping, bars, sizes, durations and dates."""

import html
from datetime import datetime, timedelta, timezone

import messages
from messages import t

LIGHTS = {"ok": "🟢", "warn": "🟡", "bad": "🔴"}


def esc(value):
    return html.escape(str(value), quote=False)


def number(value, decimals=0):
    text = f"{value:,.{decimals}f}"
    if messages.language() == "es":
        text = text.replace(",", " ").replace(".", ",").replace(" ", ".")
    return text


def size(n):
    """Bytes in a readable unit: 512 B, 980 MB, 1,9 GB."""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            decimals = 1 if unit != "B" and value < 10 else 0
            return f"{number(value, decimals)} {unit}"
        value /= 1024


def bar(pct, width=10):
    filled = max(0, min(width, int(pct * width / 100 + 0.5)))  # half up: 25 % fills 3 of 10
    return "▰" * filled + "▱" * (width - filled)


def meter(label, pct, label_width=5):
    """A monospace line such as «RAM   ▰▰▱▱▱▱▱▱▱▱  24%», so several of them line up."""
    return f"<code>{esc(label.ljust(label_width))} {bar(pct)} {int(round(pct)):>3}%</code>"


def level(pct, limit):
    """ok, warn (within 10 points of the limit) or bad (at the limit or above)."""
    if pct >= limit:
        return "bad"
    return "warn" if pct >= limit - 10 else "ok"


def light(state):
    return LIGHTS[state]


def duration(seconds):
    minutes = int(max(seconds, 0)) // 60
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return t("dur_days", d=days, h=hours)
    if hours:
        return t("dur_hours", h=hours, m=mins)
    return t("dur_minutes", m=mins)


def ago(when, now):
    return t("ago", d=duration((now - when).total_seconds()))


def clock(when):
    return when.strftime("%H:%M")


def day(when, now):
    """«hoy a las 04:30», «ayer a las 23:10» or «28 oct a las 04:30»."""
    days = (now.date() - when.date()).days
    if days == 0:
        return t("today_at", time=clock(when))
    if days == 1:
        return t("yesterday_at", time=clock(when))
    return t("date_at", day=when.day, month=t("months").split(",")[when.month - 1], time=clock(when))


def stamp(now):
    """Header date: «jueves 30 oct · 09:00»."""
    return t("stamp", weekday=t("weekdays").split(",")[now.weekday()], day=now.day,
             month=t("months").split(",")[now.month - 1], time=clock(now))


def parse_time(text, tz):
    """ISO date from a probe or rclone (2026-10-30T04:30:12.123456789+01:00, …Z, …+0100) → local datetime."""
    text = text.strip()
    base = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
    rest = text[19:].lstrip("0123456789.")
    if rest in ("", "Z"):
        offset = timedelta(0) if rest == "Z" else None
    else:
        sign = -1 if rest[0] == "-" else 1
        digits = rest[1:].replace(":", "")
        offset = sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0))
    if offset is None:
        return base.replace(tzinfo=tz)
    return base.replace(tzinfo=timezone(offset)).astimezone(tz)


def host(url):
    """https://example.com/ → example.com, for short labels."""
    return url.split("://", 1)[-1].rstrip("/")
