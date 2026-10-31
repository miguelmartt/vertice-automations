"""UptimeRobot webhook: forwards its down/up alerts to Telegram.

Listens on 127.0.0.1 only; put nginx (or any reverse proxy) in front for HTTPS. A request only counts
if it carries WEBHOOK_TOKEN, as the "token" field of its JSON body or query string, or in an
X-Webhook-Token header. Any other path, any GET and a missing or wrong token all get the same 404,
and nothing is sent. At most MAX_PER_MINUTE alerts a minute reach Telegram; the ones over it are
counted and summed up in a single message, so a flood can't push the bot into Telegram's own limits.
"""

import hmac
import json
import logging
import re
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fmt import esc
from messages import t

log = logging.getLogger("uptimerobot")
MAX_BODY = 65536
MAX_FIELDS = 100
MAX_PER_MINUTE = 20
MIN_TOKEN = 16
TIMEOUT = 10  # seconds a client gets to send its request; a stalled one is dropped
LENGTH = re.compile(r"[0-9]{1,10}")


def server(telegram, chat_id, port, path, token, per_minute=MAX_PER_MINUTE):
    if len(token) < MIN_TOKEN:
        raise ValueError(f"the webhook token must have at least {MIN_TOKEN} characters")
    path = "/" + path.strip("/")
    expected = token.encode()
    flood = Flood(per_minute, lambda n: telegram.send(chat_id, t("external_flood", n=n, limit=per_minute), html=True))

    class Webhook(BaseHTTPRequestHandler):
        timeout = TIMEOUT

        def do_POST(self):
            url = urllib.parse.urlsplit(self.path)
            if url.path.rstrip("/") != path:
                return self.reply(404)
            length = self.headers.get("Content-Length", "").strip()
            if not LENGTH.fullmatch(length):
                return self.reply(400)  # missing, negative or not a number (a chunked body, for example)
            if int(length) > MAX_BODY:
                return self.reply(413)
            data = fields(url.query, self.rfile.read(int(length)))
            given = self.headers.get("X-Webhook-Token") or data.pop("token", "")
            if not hmac.compare_digest(str(given).encode("utf-8", "surrogatepass"), expected):
                return self.reply(404)
            if not flood.allow():
                return self.reply(200)  # counted for the summary; a retry would only add to the flood
            try:
                telegram.send(chat_id, alert(data), html=True)
            except Exception:
                log.exception("Could not forward the UptimeRobot alert")
                return self.reply(502)
            log.info("UptimeRobot alert forwarded")
            self.reply(200)

        def do_GET(self):
            self.reply(404)

        def reply(self, code):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": code == 200}).encode())

        def log_message(self, *args):
            pass  # no per-request log: bots crawling the domain would fill it with 404s

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Webhook)
    httpd.flood = flood
    return httpd


def fields(query, raw):
    """The alert as a dict: UptimeRobot can send it as JSON, as a form or in the query string."""
    data = form(query)
    try:
        body = json.loads(raw or b"{}")
    except (ValueError, RecursionError):  # not JSON (a form, then), or nested deep enough to exhaust the stack
        body = form(raw.decode(errors="replace"))
    if isinstance(body, dict):
        data.update(body)
    return data


def form(text):
    try:
        return dict(urllib.parse.parse_qsl(text, max_num_fields=MAX_FIELDS))
    except ValueError:
        return {}


class Flood:
    """Lets `limit` alerts a minute through. The rest are dropped and counted, and when that minute
    is over, report(count) is called once."""

    def __init__(self, limit, report, window=60.0, clock=time.monotonic):
        self.limit, self.report, self.window, self.clock = limit, report, window, clock
        self.lock = threading.Lock()
        self.start, self.count, self.dropped = None, 0, 0

    def allow(self):
        with self.lock:
            now = self.clock()
            if self.start is None or now - self.start >= self.window:
                self.start, self.count = now, 0
            self.count += 1
            if self.count <= self.limit:
                return True
            self.dropped += 1
            first, wait = self.dropped == 1, self.start + self.window - now
        if first:
            timer = threading.Timer(max(wait, 0), self.flush)
            timer.daemon = True
            timer.start()
        return False

    def flush(self):
        with self.lock:
            dropped, self.dropped = self.dropped, 0
        if not dropped:
            return
        log.warning("Dropped %d UptimeRobot alerts over the limit of %d a minute", dropped, self.limit)
        try:
            self.report(dropped)
        except Exception:
            log.exception("Could not send the summary of the dropped UptimeRobot alerts")


def alert(b):
    kind = str(b["alertType"] if b.get("alertType") is not None else b.get("alertTypeFriendlyName", "")).lower()
    down = kind == "1" or "down" in kind
    lines = [
        t("external_down" if down else "external_up"),
        "• " + t("external_monitor", value=esc(b.get("monitor") or b.get("monitorFriendlyName") or "?")),
        "• " + t("external_url", value=esc(b.get("url") or b.get("monitorURL") or "?")),
        "• " + t("external_details", value=esc(b.get("details") or b.get("alertDetails") or "—")),
    ]
    when = b.get("datetime") or b.get("alertDateTime")
    if when:
        lines += ["", f"<i>🕒 {esc(when)}</i>"]
    return "\n".join(lines)
