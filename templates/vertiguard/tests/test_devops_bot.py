import unittest

import messages
from devops_bot import DevopsBot
from gemini import GeminiError
from tests.fakes import FakeProbes, FakeTelegram

CHAT = 42
OUTPUTS = {
    "check_services.sh": {"ts": "t", "checks": {"nginx": "OK", "https://example.com": "FAIL(503)"}},
    "disk_ram.sh": {"ts": "t", "disk_pct": 12, "ram_pct": 34, "uptime": "up 3 days"},
    "ssl_check.sh": {"ts": "t", "certs": [{"name": "example.com", "days": 60}]},
    "fail2ban_report.sh": {"ts": "t", "configured": True, "jail": "sshd", "cur_banned": 1, "tot_banned": 5,
                           "cur_failed": 0, "tot_failed": 9, "banned_ips": "192.0.2.7"},
    "backup_watchdog.sh": {"ts": "t", "configured": False},
    "restart_service.sh": lambda *a: {"restartable": ["nginx", "mariadb"]} if a == ("--list",)
    else {"ok": True, "state": "active", "service": a[0]},
    "unban_ip.sh": lambda ip: {"ok": True, "ip": ip},
}


def message(text, chat=CHAT):
    return {"update_id": 1, "message": {"chat": {"id": chat}, "text": text}}


def button(data, chat=CHAT):
    return {"update_id": 1, "callback_query": {"id": "cq", "data": data, "message": {"chat": {"id": chat}}}}


class FakeGemini:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def generate(self, contents, system=None, tools=None):
        self.requests.append(list(contents))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def text_response(text):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]}


class DevopsBotTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")
        self.tg = FakeTelegram()
        self.probes = FakeProbes(OUTPUTS)
        self.bot = DevopsBot(self.tg, CHAT, self.probes)

    def test_ignores_other_chats(self):
        self.bot.handle(message("/menu", chat=7))
        self.bot.handle(button("r:status", chat=7))
        self.assertEqual(self.tg.sent, [])
        self.assertEqual(self.probes.ran, [])

    def test_menu_has_restart_buttons_from_the_probe(self):
        self.bot.handle(message("/menu"))
        keyboard = self.tg.sent[0]["reply_markup"]["inline_keyboard"]
        data = [b["callback_data"] for row in keyboard for b in row]
        self.assertIn("c:restart:nginx", data)
        self.assertIn("c:restart:mariadb", data)
        self.assertIn("c:unban", data)

    def test_status_button(self):
        self.bot.handle(button("r:status"))
        text = self.tg.texts[0]
        self.assertIn("nginx: OK", text)
        self.assertIn("https://example.com: FAIL(503)", text)
        self.assertIn("Disk: 12% | RAM: 34%", text)
        self.assertEqual(self.tg.calls[0][0], "answerCallbackQuery")

    def test_backups_not_configured(self):
        self.bot.handle(button("r:backups"))
        self.assertEqual(self.tg.texts[0], "Not configured.")

    def test_restart_asks_before_doing_it(self):
        self.bot.handle(button("c:restart:nginx"))
        self.assertNotIn(("restart_service.sh", "nginx"), self.probes.ran)
        self.assertIn("Confirm?", self.tg.texts[0])
        self.bot.handle(button("ok:restart:nginx"))
        self.assertIn(("restart_service.sh", "nginx"), self.probes.ran)
        self.assertEqual(self.tg.texts[1], "nginx restarted (active).")

    def test_unban_validates_the_ip(self):
        self.bot.handle(button("ok:unban:1.2.3.4; rm -rf /"))
        self.assertEqual(self.tg.texts[0], "Invalid IP.")
        self.assertFalse(any(r[0] == "unban_ip.sh" for r in self.probes.ran))
        self.bot.handle(button("ok:unban:192.0.2.7"))
        self.assertEqual(self.tg.texts[1], "IP unbanned: 192.0.2.7")

    def test_unknown_button(self):
        self.bot.handle(button("c:n8n"))
        self.assertIn("no longer exists", self.tg.texts[0])

    def test_text_without_gemini_points_to_menu(self):
        self.bot.handle(message("how is the server?"))
        self.assertEqual(self.tg.texts, ["Send /menu to see the options."])


class GeminiChatTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")
        self.tg = FakeTelegram()
        self.probes = FakeProbes(OUTPUTS)

    def test_tool_call_then_answer(self):
        call = {"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "get_server_status", "args": {}}, "thoughtSignature": "sig"}]}}]}
        gemini = FakeGemini([call, text_response("All good.")])
        bot = DevopsBot(self.tg, CHAT, self.probes, gemini)
        bot.handle(message("how is the server?"))
        self.assertEqual(self.tg.texts, ["All good."])
        second = gemini.requests[1]
        self.assertEqual(second[1]["parts"][0]["thoughtSignature"], "sig")
        snapshot = second[2]["parts"][0]["functionResponse"]["response"]["snapshot"]
        self.assertEqual(snapshot["resources"]["disk_pct"], 12)
        self.assertEqual(len(bot.memory), 2)

    def test_gemini_failure_gives_a_friendly_answer(self):
        bot = DevopsBot(self.tg, CHAT, self.probes, FakeGemini([GeminiError("HTTP 500")]))
        with self.assertLogs("bot", level="ERROR"):
            bot.handle(message("hello"))
        self.assertIn("Gemini failed", self.tg.texts[0])
        self.assertEqual(len(bot.memory), 0)


if __name__ == "__main__":
    unittest.main()
