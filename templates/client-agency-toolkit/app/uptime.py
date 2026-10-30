"""Client uptime monitor: checks each site and alerts on Telegram when its status changes.

No response or HTTP >= 500 is "down", HTTP >= 400 is "warning", anything else is "up". The last
status of each site is kept in the state file, so a restart does not repeat an alert.
"""

import concurrent.futures
import http.client
import logging
import urllib.error
import urllib.request

from config import ConfigError

log = logging.getLogger("uptime")

UP, WARNING, DOWN = "up", "warning", "down"
USER_AGENT = "Mozilla/5.0 (compatible; agency-toolkit uptime monitor)"
MAX_WORKERS = 8


def missing_settings(settings):
    return [] if settings.get_list("UPTIME_SITES") else ["UPTIME_SITES"]


def parse_sites(settings):
    """UPTIME_SITES: comma-separated "Label|URL" items ("URL" alone uses the URL as the label)."""
    sites = []
    for item in settings.get_list("UPTIME_SITES"):
        label, _, url = item.rpartition("|")
        label, url = label.strip(), url.strip()
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"UPTIME_SITES: {item!r} should look like 'Client A|https://example.com'")
        sites.append((label or url, url))
    return sites


def check(url, timeout):
    """(HTTP status, None) when the site answers, (None, reason) when it does not. Redirects are followed."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, None
    except urllib.error.HTTPError as e:
        e.close()
        return e.code, None
    except (OSError, http.client.HTTPException, ValueError) as e:
        return None, str(getattr(e, "reason", e)) or type(e).__name__


def classify(status):
    if status is None or status >= 500:
        return DOWN
    if status >= 400:
        return WARNING
    return UP


class Monitor:
    """alert(text) sends a Telegram message; check(url, timeout) can be replaced in tests."""

    def __init__(self, sites, alert, state, texts, timeout=10, check=check):
        self.sites = sites
        self.alert = alert
        self.state = state
        self.texts = texts
        self.timeout = timeout
        self.check = check

    def run(self):
        workers = max(1, min(MAX_WORKERS, len(self.sites)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda site: self.check(site[1], self.timeout), self.sites))

        known = dict(self.state.get("uptime") or {})
        for (label, url), (status, reason) in zip(self.sites, results):
            current = classify(status)
            previous = known.get(url, UP)
            if current == previous:
                continue
            # Saved only once the alert is out: if Telegram fails, the next run tries again.
            self.alert(self.message(label, url, current, status, reason))
            log.info("%s: %s -> %s", url, previous, current)
            known[url] = current
            self.state.set("uptime", known)

        watched = {url for _, url in self.sites}
        if any(url not in watched for url in known):
            self.state.set("uptime", {url: s for url, s in known.items() if url in watched})

    def message(self, label, url, current, status, reason):
        if current == DOWN:
            key = "site_unreachable" if status is None else "site_down"
        elif current == WARNING:
            key = "site_warning"
        else:
            key = "site_recovered"
        return self.texts[key].format(label=label, url=url, status=status, reason=reason)
