"""UptimeRobot webhook: forwards its down/up alerts to Telegram.

Listens on 127.0.0.1 only; put nginx (or any reverse proxy) in front for HTTPS. Any path other than
WEBHOOK_PATH gets a 404.
"""

import json
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fmt import esc
from messages import t

log = logging.getLogger("uptimerobot")
MAX_BODY = 65536


def server(telegram, chat_id, port, path):
    path = "/" + path.strip("/")

    class Webhook(BaseHTTPRequestHandler):
        def do_POST(self):
            url = urllib.parse.urlsplit(self.path)
            if url.path.rstrip("/") != path:
                return self.reply(404)
            # UptimeRobot can send the data as JSON, as a form or in the query string.
            data = dict(urllib.parse.parse_qsl(url.query))
            raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), MAX_BODY))
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = dict(urllib.parse.parse_qsl(raw.decode(errors="replace")))
            if isinstance(body, dict):
                data.update(body)
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

    return ThreadingHTTPServer(("127.0.0.1", port), Webhook)


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
