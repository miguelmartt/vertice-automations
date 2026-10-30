"""The VertiGuard bot on Telegram: commands, a panel of buttons and questions to Gemini.

Commands go in the configured language (/parte, /servicios… or /report, /services…) and the
English names always work too. Telegram shows them in its «/» menu. Buttons edit the message they
belong to, so browsing the panel does not flood the chat. Restarts ask first, and only the units in
probes.conf's RESTARTABLE can be restarted (the root probe checks it, not the bot). Gemini can read
a snapshot of the server but cannot change anything. Only the configured chat gets an answer.
"""

import ipaddress
import logging
from collections import deque

import messages
import panels
from fmt import esc
from gemini import GeminiError, answer_text, model_turn
from messages import t
from telegram import TelegramError

log = logging.getLogger("bot")

ORDER = ["report", "services", "resources", "security", "backups", "ssl", "docker", "updates",
         "menu", "restart", "unban", "help"]
SYSTEM = (
    "You are VertiGuard, the assistant that watches the user's self-hosted server, reached over Telegram. "
    "When the user asks about the server (services, websites, CPU, RAM, disks, SSL, attacks, SSH logins, "
    "backups, Docker, updates), call get_server_status for live data and answer from it. You can only read: "
    "to restart a service or unban an IP, tell them to use /menu. Answer in the user's language, short and "
    "concrete, plain text without Markdown. For unrelated questions, just help."
)
TOOLS = [{"functionDeclarations": [{
    "name": "get_server_status",
    "description": "Live read-only snapshot of the server: services and websites, CPU, RAM, disks, top "
                   "processes, SSL days left, fail2ban, SSH logins, backups, Docker and pending updates. No input.",
}]}]
MAX_TOOL_ROUNDS = 5


def command_names():
    """{word: key}, in the configured language and in English."""
    names = {"start": "help"}
    for lang in ("en", messages.language()):
        for key in ORDER:
            names[messages.TEXTS[lang]["cmd_" + key]] = key
    return names


def keyboard(*rows):
    return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row] for row in rows]}


def back_to_menu():
    return keyboard([(t("btn_menu"), "m")])


class Bot:
    def __init__(self, telegram, chat_id, snapshot, probes, context, gemini=None, report_hour=9):
        self.tg = telegram
        self.chat_id = chat_id
        self.snapshot = snapshot
        self.probes = probes
        self.context = context  # callable → panels.Context with the current time
        self.gemini = gemini
        self.report_hour = report_hour
        self.memory = deque(maxlen=20)  # the last 10 exchanges with Gemini
        self.commands = command_names()

    # ── Telegram plumbing ───────────────────────────────────────────────────────────────────────

    def setup(self):
        """The «/» command list and the bot's description in Telegram. A failure only logs."""
        try:
            self.tg.call("setMyCommands", {"commands": [
                {"command": t("cmd_" + key), "description": t("desc_" + key)} for key in ORDER]})
            self.tg.call("setMyDescription", {"description": t("bot_description")})
            self.tg.call("setMyShortDescription", {"short_description": t("bot_short_description")})
        except TelegramError as e:
            log.warning("Could not set the bot's commands and description: %s", e)

    def loop(self, stop):
        self.setup()
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
                self.on_button(cq)
                return
            text = (msg.get("text") or "").strip()
            if text.startswith("/"):
                key = self.commands.get(text[1:].split()[0].split("@")[0].lower()) if len(text) > 1 else None
                self.on_command(key) if key else self.send(t("use_menu"))
            elif text:
                self.chat(text)
        except Exception as e:
            log.exception("A Telegram command failed")
            self.send(t("action_failed", error=esc(str(e)[:300])))

    def send(self, text, reply_markup=None):
        extra = {"reply_markup": reply_markup} if reply_markup else {}
        self.tg.send(self.chat_id, text, html=True, **extra)

    # ── Commands and buttons ─────────────────────────────────────────────────────────────────────

    def on_command(self, key):
        if key == "menu":
            self.send(*self.menu())
        elif key == "help":
            self.send(self.help(), self.menu()[1])
        elif key == "restart":
            self.send(*self.restart_list())
        elif key == "unban":
            self.send(*self.unban_list())
        else:
            self.send(*self.view(key))

    def on_button(self, cq):
        data = cq.get("data", "")
        refresh = data.startswith("r:")
        # Answer right away so the button stops spinning; the edit comes after.
        self.tg.call("answerCallbackQuery", {"callback_query_id": cq["id"], **({"text": t("refreshed")} if refresh else {})})
        if data in ("m", "x"):
            text, markup = self.menu()
        elif data[:2] in ("v:", "r:") and data[2:] in panels.VIEWS:
            text, markup = self.view(data[2:], fresh=refresh)
        elif data == "c:restart":
            text, markup = self.restart_list()
        elif data.startswith("c:restart:"):
            unit = data[len("c:restart:"):]
            text = t("restart_confirm", name=esc(unit))
            markup = keyboard([(t("btn_confirm_restart"), "ok:restart:" + unit), (t("btn_cancel"), "m")])
        elif data.startswith("ok:restart:"):
            text, markup = self.restart(data[len("ok:restart:"):])
        elif data == "c:unban":
            text, markup = self.unban_list()
        elif data.startswith("ok:unban:"):
            text, markup = self.unban(data[len("ok:unban:"):])
        else:
            text, markup = t("stale_option"), back_to_menu()
        message_id = (cq.get("message") or {}).get("message_id")
        if message_id:
            self.tg.edit(self.chat_id, message_id, text, html=True, reply_markup=markup)
        else:
            self.send(text, markup)

    def view(self, key, fresh=False):
        names, build = panels.VIEWS[key]
        text = build(self.snapshot.read(names, fresh=fresh), self.context())
        return text, keyboard([(t("btn_refresh"), "r:" + key), (t("btn_menu"), "m")])

    def menu(self):
        rows = [
            [(t("btn_report"), "v:report"), (t("btn_services"), "v:services")],
            [(t("btn_resources"), "v:resources"), (t("btn_security"), "v:security")],
            [(t("btn_backups"), "v:backups"), (t("btn_ssl"), "v:ssl")],
            [(t("btn_docker"), "v:docker"), (t("btn_updates"), "v:updates")],
            [(t("btn_restart"), "c:restart"), (t("btn_unban"), "c:unban")],
        ]
        return t("menu_text", server=esc(self.context().server)), keyboard(*rows)

    def help(self):
        intro = t("help_intro", server=esc(self.context().server))
        if self.report_hour is not None:
            intro += " " + t("help_daily", hour=self.report_hour)
        parts = [intro, "\n".join(f"/{t('cmd_' + key)} · {t('desc_' + key)}" for key in ORDER)]
        if self.gemini:
            parts.append(t("help_ai"))
        return "\n\n".join(parts)

    def restart_list(self):
        units = self.probes.run("restart_service.sh", "--list")["restartable"]
        if not units:
            return t("restart_none"), back_to_menu()
        rows = [[("🔄 " + unit, "c:restart:" + unit)] for unit in units]
        return t("restart_pick"), keyboard(*rows, [(t("btn_back"), "m")])

    def restart(self, unit):
        d = self.probes.run("restart_service.sh", unit)
        if d.get("ok"):
            return t("restarted", name=esc(unit), state=esc(d.get("state") or "?")), back_to_menu()
        return t("restart_failed", name=esc(unit), reason=esc(d.get("error") or d.get("state") or "?")), back_to_menu()

    def unban_list(self):
        ips = (self.probes.run("fail2ban_report.sh").get("banned_ips") or "").split()
        if not ips:
            return t("no_banned"), back_to_menu()
        buttons = [("🚫 " + ip, "ok:unban:" + ip) for ip in ips[:30]]
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        return t("unban_pick"), keyboard(*rows, [(t("btn_back"), "m")])

    def unban(self, ip):
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return t("invalid_ip"), back_to_menu()
        d = self.probes.run("unban_ip.sh", ip)
        if d.get("ok"):
            return t("unbanned", ip=esc(ip)), back_to_menu()
        return t("unban_failed", ip=esc(ip), reason=esc(d.get("error") or d.get("detail") or "?")), back_to_menu()

    # ── Questions in plain words ─────────────────────────────────────────────────────────────────

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
        data = self.snapshot.read()
        backups = data.get("backups") or {}
        if isinstance(backups.get("files"), list):
            data["backups"] = dict(backups, files=backups["files"][-5:])
        return {"snapshot": data}
