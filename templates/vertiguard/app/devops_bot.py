"""DevOps bot for Telegram.

/menu shows buttons to read the server status, restart the services allowed in probes.conf (with a
confirmation step) and unban IPs. Any other text goes to Gemini, which can read the server status
but cannot change anything. The bot only answers the configured chat.
"""

import ipaddress
import logging
from collections import deque

from gemini import GeminiError, answer_text, model_turn
from messages import t
from probes import ProbeError
from telegram import TelegramError

log = logging.getLogger("bot")

SYSTEM = (
    "You are the DevOps assistant for the user's self-hosted VPS, reached over Telegram. "
    "When the user asks about the server's health (services, disk, RAM, uptime, SSL, fail2ban/attacks, backups), "
    "call the get_server_status tool for a live snapshot and answer using that data. "
    "To run quick actions or see buttons (restart services, unban IP, check status), tell them to send /menu. "
    "Answer in the user's language, concise, plain text, no emojis. For unrelated questions, just help."
)
TOOLS = [{"functionDeclarations": [{
    "name": "get_server_status",
    "description": "Fetch a LIVE read-only snapshot of the server (services, disk %, RAM %, uptime, SSL days, "
                   "fail2ban, backups). Call it when the user asks about the server. No input.",
}]}]
SNAPSHOT = {
    "services": "check_services.sh",
    "resources": "disk_ram.sh",
    "ssl": "ssl_check.sh",
    "fail2ban": "fail2ban_report.sh",
    "backups": "backup_watchdog.sh",
}
MAX_TOOL_ROUNDS = 5


class DevopsBot:
    def __init__(self, telegram, chat_id, probes, gemini=None):
        self.tg = telegram
        self.chat_id = chat_id
        self.probes = probes
        self.gemini = gemini
        self.memory = deque(maxlen=20)  # the last 10 exchanges

    def loop(self, stop):
        offset = 0
        while not stop.is_set():
            try:
                updates = self.tg.updates(offset)
            except TelegramError as e:
                log.warning("%s", e)
                stop.wait(5)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                try:
                    self.handle(u)
                except Exception:
                    log.exception("Could not handle an update")

    def handle(self, update):
        cq, msg = update.get("callback_query"), update.get("message")
        chat = ((cq or {}).get("message") or msg or {}).get("chat", {}).get("id")
        if chat != self.chat_id:
            return
        try:
            if cq:
                self.tg.call("answerCallbackQuery", {"callback_query_id": cq["id"]})
                self.button(cq.get("data", ""))
                return
            text = (msg.get("text") or "").strip()
            if text.lower().split("@")[0] in ("/menu", "/start"):
                self.send(t("menu"), reply_markup=self.menu())
            elif text:
                self.chat(text)
        except Exception as e:
            log.exception("A Telegram command failed")
            self.send(t("action_failed", error=str(e)[:300]))

    def send(self, text, **extra):
        self.tg.send(self.chat_id, text, **extra)

    def menu(self):
        rows = [
            [{"text": t("btn_status"), "callback_data": "r:status"}],
            [{"text": t("btn_disk"), "callback_data": "r:disk"}, {"text": t("btn_ram"), "callback_data": "r:ram"},
             {"text": t("btn_uptime"), "callback_data": "r:uptime"}],
            [{"text": t("btn_ssl"), "callback_data": "r:ssl"}, {"text": t("btn_f2b"), "callback_data": "r:f2b"},
             {"text": t("btn_backups"), "callback_data": "r:backups"}],
        ]
        restart = [{"text": t("btn_restart", name=unit), "callback_data": "c:restart:" + unit}
                   for unit in self.probes.run("restart_service.sh", "--list")["restartable"]]
        rows += [restart[i:i + 2] for i in range(0, len(restart), 2)]
        rows.append([{"text": t("btn_unban"), "callback_data": "c:unban"}])
        return {"inline_keyboard": rows}

    def button(self, data):
        if data.startswith("r:"):
            self.send(self.read(data[2:]))
        elif data.startswith("c:restart:"):
            unit = data[len("c:restart:"):]
            self.send(t("confirm_restart", name=unit), reply_markup={"inline_keyboard": [[
                {"text": t("btn_confirm"), "callback_data": "ok:restart:" + unit},
                {"text": t("btn_cancel"), "callback_data": "x"},
            ]]})
        elif data.startswith("ok:restart:"):
            self.restart(data[len("ok:restart:"):])
        elif data == "c:unban":
            self.pick_ip()
        elif data.startswith("ok:unban:"):
            self.unban(data[len("ok:unban:"):])
        elif data == "x":
            self.send(t("cancelled"))
        else:
            self.send(t("stale_option"))

    def read(self, what):
        """Text for each read-only button, from the probe that answers it."""
        if what == "status":
            s = self.probes.run("check_services.sh")["checks"]
            r = self.probes.run("disk_ram.sh")
            return "\n".join([t("status_title")]
                             + [f"{k}: {'OK' if str(v).startswith('OK') else v}" for k, v in s.items()]
                             + [t("status_resources", disk=r["disk_pct"], ram=r["ram_pct"]), r.get("uptime", "")])
        if what in ("disk", "ram", "uptime"):
            r = self.probes.run("disk_ram.sh")
            return {"disk": t("disk", pct=r["disk_pct"]), "ram": t("ram", pct=r["ram_pct"]),
                    "uptime": t("uptime", value=r.get("uptime") or "-")}[what]
        if what == "ssl":
            certs = self.probes.run("ssl_check.sh")["certs"]
            return "\n".join([t("ssl_title")] + [t("ssl_item", name=c["name"], days=c["days"]) for c in certs])
        if what == "f2b":
            f = self.probes.run("fail2ban_report.sh")
            if not f.get("configured"):
                return t("not_configured")
            return t("f2b_report", jail=f["jail"], cur_banned=f["cur_banned"], tot_banned=f["tot_banned"],
                     cur_failed=f["cur_failed"], tot_failed=f["tot_failed"], ips=f["banned_ips"] or "-")
        if what == "backups":
            b = self.probes.run("backup_watchdog.sh")
            if not b.get("configured"):
                return t("not_configured")
            status = t("backups_today_ok") if b["today_count"] else t("backups_today_missing")
            return t("backups_report", today=b["today"], today_status=status, newest=b["newest"] or "-")
        return t("stale_option")

    def restart(self, unit):
        d = self.probes.run("restart_service.sh", unit)
        if d.get("ok"):
            self.send(t("restarted", name=unit, state=d.get("state") or "?"))
        else:
            self.send(t("restart_failed", name=unit, reason=d.get("error") or d.get("state") or "?"))

    def pick_ip(self):
        f = self.probes.run("fail2ban_report.sh")
        ips = f.get("banned_ips", "").split()
        if not ips:
            return self.send(t("no_banned"))
        rows = [[{"text": t("btn_unban_ip", ip=ip), "callback_data": "ok:unban:" + ip}] for ip in ips[:50]]
        self.send(t("pick_ip"), reply_markup={"inline_keyboard": rows + [[{"text": t("btn_cancel"), "callback_data": "x"}]]})

    def unban(self, ip):
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return self.send(t("invalid_ip"))
        d = self.probes.run("unban_ip.sh", ip)
        if d.get("ok"):
            self.send(t("unbanned", ip=ip))
        else:
            self.send(t("unban_failed", ip=ip, reason=d.get("error") or d.get("detail") or "?"))

    def chat(self, text):
        if self.gemini is None:
            return self.send(t("use_menu"))
        self.tg.call("sendChatAction", {"chat_id": self.chat_id, "action": "typing"})
        try:
            reply = self.ask_gemini(text) or t("no_answer")
        except Exception:
            log.exception("Gemini did not answer")
            reply = t("ai_failed")
        self.tg.send_long(self.chat_id, reply)

    def ask_gemini(self, text):
        question = {"role": "user", "parts": [{"text": text}]}
        contents = list(self.memory) + [question]
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.gemini.generate(contents, system=SYSTEM, tools=TOOLS)
            turn = model_turn(response)
            calls = [p["functionCall"] for p in turn.get("parts", []) if "functionCall" in p]
            if not calls:
                reply = answer_text(response)
                if reply:
                    self.memory.extend([question, {"role": "model", "parts": [{"text": reply}]}])
                return reply
            # The turn goes back untouched: newer models require their thought signature back.
            contents += [turn, {"role": "user", "parts": [
                {"functionResponse": {"name": c["name"], "response": self.tool(c["name"])}} for c in calls
            ]}]
        raise GeminiError(f"Gemini did not finish after {MAX_TOOL_ROUNDS} tool calls")

    def tool(self, name):
        if name != "get_server_status":
            return {"error": f"unknown tool {name}"}
        snapshot = {}
        for key, probe in SNAPSHOT.items():
            try:
                snapshot[key] = self.probes.run(probe)
            except ProbeError as e:
                snapshot[key] = {"error": str(e)}
        return {"snapshot": snapshot}
