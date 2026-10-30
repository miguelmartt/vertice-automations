"""Weekly analytics report: visitors, pageviews, top pages and top sources -> HTML email.

The numbers come from the Plausible Stats API (Cloud or self-hosted) or, with
ANALYTICS_PROVIDER=umami, from the Umami API. The service sends it on schedule; to try it by hand:

  python3 report.py [--config /etc/agency-toolkit/agency-toolkit.env] [--dry-run]

--dry-run prints the HTML to stdout instead of emailing it.
"""

import argparse
import html
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta
from string import Template

import config
import mailer
import messages

log = logging.getLogger("report")

DEFAULT_CONFIG = "/etc/agency-toolkit/agency-toolkit.env"
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html")
PROVIDERS = {"plausible": "Plausible", "umami": "Umami"}
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TOP = 5
TIMEOUT = 30
USER_AGENT = "agency-toolkit weekly report"


class ReportError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


# --- Settings -------------------------------------------------------------------------------------

def provider(settings):
    name = settings.get_str("ANALYTICS_PROVIDER", "plausible").lower()
    if name not in PROVIDERS:
        raise config.ConfigError(f"ANALYTICS_PROVIDER must be plausible or umami, not {name!r}")
    return name


def missing_settings(settings):
    if settings.get_str("ANALYTICS_PROVIDER", "plausible").lower() == "umami":
        missing = [key for key in ("UMAMI_API_URL", "UMAMI_WEBSITE_ID") if not settings.get_str(key)]
        login = settings.get_str("UMAMI_USERNAME") and settings.get_str("UMAMI_PASSWORD")
        if not settings.get_str("UMAMI_API_KEY") and not login:
            missing.append("UMAMI_API_KEY")
    else:
        missing = [key for key in ("PLAUSIBLE_SITE_ID", "PLAUSIBLE_API_KEY") if not settings.get_str(key)]
    if not settings.get_list("REPORT_TO"):
        missing.append("REPORT_TO")
    return missing


def schedule(settings):
    """(weekday, hour, minute) from REPORT_DAY (monday...) and REPORT_TIME (HH:MM)."""
    day = settings.get_str("REPORT_DAY", "monday").lower()[:3]
    if day not in DAYS:
        raise config.ConfigError(f"REPORT_DAY must be a weekday name like monday, not {settings.get('REPORT_DAY')!r}")
    value = settings.get_str("REPORT_TIME", "09:00")
    try:
        hour, minute = (int(part) for part in value.split(":"))
        time(hour, minute)
    except ValueError:
        raise config.ConfigError(f"REPORT_TIME must look like 09:00, not {value!r}") from None
    return DAYS.index(day), hour, minute


def zone(settings):
    """TIMEZONE (Europe/Madrid, for example), or None for the server's local time."""
    name = settings.get_str("TIMEZONE")
    if not name:
        return None
    from zoneinfo import ZoneInfo  # Only needed when TIMEZONE is set.
    try:
        return ZoneInfo(name)
    except (LookupError, ValueError):
        raise config.ConfigError(f"TIMEZONE {name!r} is not a known time zone") from None


def site_name(settings):
    key = "UMAMI_WEBSITE_ID" if provider(settings) == "umami" else "PLAUSIBLE_SITE_ID"
    return settings.get_str("REPORT_SITE_NAME") or settings.get_str(key)


def period(today, days):
    """The last `days` full days, ending yesterday: on a Monday with days=7, last Monday to Sunday."""
    if days < 1:
        raise config.ConfigError("REPORT_DAYS must be 1 or more")
    end = today - timedelta(days=1)
    return end - timedelta(days=days - 1), end


# --- Fetching the numbers -------------------------------------------------------------------------

def request_json(url, headers, data=None):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT, **headers}
    if body is not None:
        headers["Content-Type"] = "application/json"
    where = url.split("?")[0]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=TIMEOUT) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        e.close()
        raise ReportError(f"{where}: HTTP {e.code} {detail}", e.code) from None
    except OSError as e:
        raise ReportError(f"{where}: {getattr(e, 'reason', e)}") from None
    except ValueError:
        raise ReportError(f"{where} did not answer with JSON") from None


def value(item):
    """A metric as a number, whether the API sends 12, "12" or {"value": 12}."""
    if isinstance(item, dict):
        item = item.get("value")
    try:
        return float(item or 0)
    except (TypeError, ValueError):
        return 0.0


def fetch_plausible(settings, start, end):
    """Stats API v1, as the n8n version: one aggregate call and two breakdowns."""
    base = settings.get_str("PLAUSIBLE_URL", "https://plausible.io").rstrip("/") + "/api/v1/stats/"
    headers = {"Authorization": "Bearer " + settings.need("PLAUSIBLE_API_KEY")}
    query = {"site_id": settings.need("PLAUSIBLE_SITE_ID"), "period": "custom", "date": f"{start},{end}"}

    def get(endpoint, **params):
        return request_json(base + endpoint + "?" + urllib.parse.urlencode({**query, **params}), headers)

    totals = get("aggregate", metrics="visitors,pageviews,bounce_rate,visit_duration").get("results") or {}
    pages = get("breakdown", property="event:page", metrics="visitors", limit=TOP).get("results") or []
    sources = get("breakdown", property="visit:source", metrics="visitors", limit=TOP).get("results") or []
    return {
        "visitors": value(totals.get("visitors")),
        "pageviews": value(totals.get("pageviews")),
        "bounce_rate": value(totals.get("bounce_rate")),
        "visit_duration": value(totals.get("visit_duration")),
        "pages": [(row.get("page"), value(row.get("visitors"))) for row in pages],
        "sources": [(row.get("source"), value(row.get("visitors"))) for row in sources],
    }


def umami_headers(settings, api):
    key = settings.get_str("UMAMI_API_KEY")
    if key:
        # Current Umami takes the key as a Bearer token; older Umami Cloud accounts read x-umami-api-key.
        return {"Authorization": "Bearer " + key, "x-umami-api-key": key}
    login = {"username": settings.need("UMAMI_USERNAME"), "password": settings.need("UMAMI_PASSWORD")}
    token = request_json(api + "/auth/login", {}, login).get("token")
    if not token:
        raise ReportError("Umami login did not return a token (two-factor accounts need an API key)")
    return {"Authorization": "Bearer " + token}


def fetch_umami(settings, start, end, tz):
    api = settings.need("UMAMI_API_URL").rstrip("/")
    website = api + "/websites/" + urllib.parse.quote(settings.need("UMAMI_WEBSITE_ID"))
    headers = umami_headers(settings, api)
    first = datetime.combine(start, time.min, tzinfo=tz)
    after = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    query = {"startAt": int(first.timestamp() * 1000), "endAt": int(after.timestamp() * 1000) - 1}

    def metric(*types):
        # Pages are "path" since Umami 3 and "url" before; an unknown type is answered with HTTP 400.
        for kind in types:
            params = urllib.parse.urlencode({**query, "type": kind, "limit": TOP})
            try:
                return request_json(website + "/metrics?" + params, headers)
            except ReportError as e:
                if e.status != 400 or kind == types[-1]:
                    raise

    stats = request_json(website + "/stats?" + urllib.parse.urlencode(query), headers)
    visits = value(stats.get("visits"))
    bounces = min(value(stats.get("bounces")), visits)
    return {
        "visitors": value(stats.get("visitors")),
        "pageviews": value(stats.get("pageviews")),
        "bounce_rate": round(bounces * 100 / visits) if visits else 0,
        "visit_duration": value(stats.get("totaltime")) / visits if visits else 0,
        "pages": [(row.get("x"), value(row.get("y"))) for row in metric("path", "url")],
        "sources": [(row.get("x"), value(row.get("y"))) for row in metric("referrer")],
    }


def fetch(settings, start, end, tz=None):
    if provider(settings) == "umami":
        return fetch_umami(settings, start, end, tz)
    return fetch_plausible(settings, start, end)


# --- The email ------------------------------------------------------------------------------------

def duration(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 60}m {seconds % 60}s"


def render(stats, site, start, end, texts, provider_name):
    """(subject, HTML, plain text) of the report."""
    def count(n):
        return messages.number(n, texts)

    def day(d):
        return d.strftime(texts["date_format"])

    cards = [
        (texts["visitors"], count(stats["visitors"])),
        (texts["pageviews"], count(stats["pageviews"])),
        (texts["bounce_rate"], count(stats["bounce_rate"]) + "%"),
        (texts["visit_duration"], duration(stats["visit_duration"])),
    ]
    title = texts["report_title"].format(site=site)
    period_text = texts["report_period"].format(start=day(start), end=day(end))
    footer = texts["report_footer"].format(provider=provider_name)

    def rows(pairs):
        cells = "".join(
            f'<tr><td>{html.escape(str(name or texts["direct"]))}</td><td class="r">{count(n)}</td></tr>'
            for name, n in pairs
        )
        return cells or f'<tr><td colspan="2">{html.escape(texts["no_data"])}</td></tr>'

    values = {
        "lang": texts["lang"], "title": title, "period": period_text, "footer": footer,
        "visitors_label": texts["visitors"], "visitors": cards[0][1],
        "pageviews_label": texts["pageviews"], "pageviews": cards[1][1],
        "bounce_label": texts["bounce_rate"], "bounce_rate": cards[2][1],
        "duration_label": texts["visit_duration"], "visit_duration": cards[3][1],
        "top_pages": texts["top_pages"], "page_label": texts["page"],
        "top_sources": texts["top_sources"], "source_label": texts["source"],
    }
    values = {key: html.escape(v) for key, v in values.items()}
    values.update(pages=rows(stats["pages"]), sources=rows(stats["sources"]))
    with open(TEMPLATE, encoding="utf-8") as f:
        page = Template(f.read()).substitute(values)

    def lines(pairs):
        return [f"- {name or texts['direct']}: {count(n)}" for name, n in pairs] or [f"- {texts['no_data']}"]

    plain = [title, period_text, ""] + [f"{label}: {v}" for label, v in cards]
    plain += ["", texts["top_pages"]] + lines(stats["pages"])
    plain += ["", texts["top_sources"]] + lines(stats["sources"]) + ["", footer]
    return texts["report_subject"].format(site=site), page, "\n".join(plain) + "\n"


def build(settings, texts, now):
    """Fetches the numbers for the period that ends the day before `now` and renders the email."""
    start, end = period(now.date(), settings.get_int("REPORT_DAYS", 7))
    stats = fetch(settings, start, end, now.tzinfo)
    return render(stats, site_name(settings), start, end, texts, PROVIDERS[provider(settings)])


def send(settings, texts, now):
    subject, page, plain = build(settings, texts, now)
    mailer.send(settings, settings.get_list("REPORT_TO"), subject, plain, page)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send the weekly analytics report now.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config file (default {DEFAULT_CONFIG})")
    parser.add_argument("--dry-run", action="store_true", help="print the HTML instead of emailing it")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = config.load(args.config)
        texts = messages.load(settings.get_str("LANGUAGE", "en"))
        if args.dry_run:  # Nothing is emailed: no recipients or SMTP needed.
            missing = [key for key in missing_settings(settings) if key != "REPORT_TO"]
        else:
            missing = missing_settings(settings) + mailer.missing_settings(settings)
        if missing:
            raise config.ConfigError(f"The report is off: set {', '.join(missing)} in the config file")
        now = datetime.now(zone(settings))
        if args.dry_run:
            print(build(settings, texts, now)[1])
        else:
            send(settings, texts, now)
    except (OSError, config.ConfigError, ReportError) as e:
        log.error("%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
