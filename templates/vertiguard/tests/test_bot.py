import unittest

import messages
from bot import Bot
from gemini import GeminiError
from snapshot import Snapshot
from tests.fakes import FakeProbes, FakeTelegram, context, sample

CHAT = 42


def message(text, chat=CHAT, sender=None, kind="private"):
    return {"update_id": 1, "message": {"chat": {"id": chat, "type": kind}, "from": {"id": sender or chat},
                                        "text": text}}


def button(data, chat=CHAT, message_id=7, sender=None, kind="private"):
    return {"update_id": 1, "callback_query": {"id": "cq", "data": data, "from": {"id": sender or chat},
                                               "message": {"chat": {"id": chat, "type": kind},
                                                           "message_id": message_id}}}


def buttons(markup):
    return [b["callback_data"] for row in markup["inline_keyboard"] for b in row]


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


class BotTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("es")
        self.tg = FakeTelegram()
        self.probes = FakeProbes(sample())
        self.bot = Bot(self.tg, CHAT, Snapshot(self.probes), self.probes, context)

    def tearDown(self):
        messages.set_language("en")

    def test_ignores_other_chats(self):
        self.bot.handle(message("/menu", chat=7))
        self.bot.handle(button("v:report", chat=7))
        self.assertEqual(self.tg.sent + self.tg.edits, [])
        self.assertEqual(self.probes.ran, [])

    def test_only_you_in_your_private_chat(self):
        # You in a group (another member could press the buttons there), someone else in a chat with your
        # ID, a channel post, a button with no sender: all ignored, restarts included.
        self.bot.handle(message("/menu", chat=-100123, sender=CHAT, kind="supergroup"))
        self.bot.handle(button("ok:restart:nginx", chat=-100123, sender=CHAT, kind="group"))
        self.bot.handle(message("/menu", sender=7))
        self.bot.handle(button("ok:restart:nginx", sender=7))
        self.bot.handle(message("/menu", kind="group"))
        self.bot.handle({"update_id": 1, "message": {"chat": {"id": CHAT, "type": "private"}, "text": "/menu"}})
        self.bot.handle({"update_id": 1, "callback_query": {"id": "cq", "data": "m", "inline_message_id": "x",
                                                            "from": {"id": CHAT}}})
        self.assertEqual(self.tg.sent + self.tg.edits + self.tg.calls, [])
        self.assertEqual(self.probes.ran, [])
        self.bot.handle(message("/menu"))
        self.assertEqual(len(self.tg.sent), 1)

    def test_setup_registers_spanish_commands(self):
        self.bot.setup()
        method, params = self.tg.calls[0]
        self.assertEqual(method, "setMyCommands")
        names = [c["command"] for c in params["commands"]]
        self.assertEqual(names[:4], ["parte", "servicios", "recursos", "seguridad"])
        self.assertIn("ayuda", names)
        self.assertEqual([m for m, _ in self.tg.calls[1:]], ["setMyDescription", "setMyShortDescription"])

    def test_commands_in_spanish_and_english(self):
        self.bot.handle(message("/servicios"))
        self.bot.handle(message("/services@vertiguard_bot"))
        self.assertEqual(len(self.tg.sent), 2)
        for sent in self.tg.sent:
            self.assertIn("⚙️ Servicios", sent["text"])
            self.assertTrue(sent["html"])
            self.assertEqual(buttons(sent["reply_markup"]), ["r:services", "m"])

    def test_report_command(self):
        self.bot.handle(message("/parte"))
        self.assertIn("Todo en orden", self.tg.texts[0])

    def test_unknown_command(self):
        self.bot.handle(message("/n8n"))
        self.assertIn("/menu", self.tg.texts[0])

    def test_help_lists_the_commands(self):
        self.bot.handle(message("/start"))
        text = self.tg.texts[0]
        self.assertIn("/parte · El parte completo, ahora", text)
        self.assertIn("Cada día a las 9:00", text)
        self.assertNotIn("con tus palabras", text)  # no Gemini key

    def test_menu_buttons_edit_the_same_message(self):
        self.bot.handle(message("/menu"))
        self.assertIn("v:report", buttons(self.tg.sent[0]["reply_markup"]))
        self.bot.handle(button("v:resources"))
        edit = self.tg.edits[0]
        self.assertEqual(edit["message_id"], 7)
        self.assertIn("📊 Recursos", edit["text"])
        self.assertEqual(self.tg.calls[0], ("answerCallbackQuery", {"callback_query_id": "cq"}))
        self.bot.handle(button("m"))
        self.assertIn("¿Qué quieres ver?", self.tg.edits[1]["text"])

    def test_refresh_reads_again_and_says_so(self):
        self.bot.handle(button("r:updates"))
        self.bot.handle(button("v:updates"))
        updates_runs = [r for r in self.probes.ran if r[0] == "updates_check.sh"]
        self.assertEqual(len(updates_runs), 1)  # the second one comes from the cache
        self.assertEqual(self.tg.calls[0][1]["text"], "Actualizado ✓")
        self.bot.handle(button("r:updates"))
        self.assertEqual(len([r for r in self.probes.ran if r[0] == "updates_check.sh"]), 2)

    def test_restart_asks_before_doing_it(self):
        self.bot.handle(message("/reiniciar"))
        self.assertEqual(buttons(self.tg.sent[0]["reply_markup"]), ["c:restart:nginx", "c:restart:mariadb", "m"])
        self.bot.handle(button("c:restart:nginx"))
        self.assertNotIn(("restart_service.sh", "nginx"), self.probes.ran)
        self.assertIn("¿Reinicio <b>nginx</b>?", self.tg.edits[0]["text"])
        self.bot.handle(button("ok:restart:nginx"))
        self.assertIn(("restart_service.sh", "nginx"), self.probes.ran)
        self.assertEqual(self.tg.edits[1]["text"], "✅ <b>nginx</b> reiniciado: active.")

    def test_unban_validates_the_ip(self):
        self.bot.handle(message("/desbanear"))
        self.assertIn("ok:unban:192.0.2.7", buttons(self.tg.sent[0]["reply_markup"]))
        self.bot.handle(button("ok:unban:1.2.3.4; rm -rf /"))
        self.assertEqual(self.tg.edits[0]["text"], "Esa IP no es válida.")
        self.assertFalse(any(r[0] == "unban_ip.sh" for r in self.probes.ran))
        self.bot.handle(button("ok:unban:192.0.2.7"))
        self.assertEqual(self.tg.edits[1]["text"], "✅ <code>192.0.2.7</code> desbaneada.")

    def test_old_buttons_from_the_previous_bot(self):
        self.bot.handle(button("r:estado"))
        self.assertIn("ya no existe", self.tg.edits[0]["text"])

    def test_plain_text_without_gemini(self):
        self.bot.handle(message("¿cómo va el servidor?"))
        self.assertIn("/menu", self.tg.texts[0])


class GeminiChatTest(unittest.TestCase):
    def setUp(self):
        messages.set_language("en")
        self.tg = FakeTelegram()
        self.probes = FakeProbes(sample())

    def test_tool_call_then_answer(self):
        call = {"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "get_server_status", "args": {}}, "thoughtSignature": "sig"}]}}]}
        gemini = FakeGemini([call, text_response("All good.")])
        bot = Bot(self.tg, CHAT, Snapshot(self.probes), self.probes, context, gemini)
        bot.handle(message("how is the server?"))
        self.assertEqual(self.tg.texts, ["All good."])
        second = gemini.requests[1]
        self.assertEqual(second[1]["parts"][0]["thoughtSignature"], "sig")
        snapshot = second[2]["parts"][0]["functionResponse"]["response"]["snapshot"]
        self.assertEqual(snapshot["system"]["cores"], 6)
        self.assertEqual(len(bot.memory), 2)

    def test_gemini_failure_gives_a_friendly_answer(self):
        bot = Bot(self.tg, CHAT, Snapshot(self.probes), self.probes, context, FakeGemini([GeminiError("HTTP 500")]))
        with self.assertLogs("bot", level="ERROR"):
            bot.handle(message("hello"))
        self.assertIn("Gemini failed", self.tg.texts[0])
        self.assertEqual(len(bot.memory), 0)


if __name__ == "__main__":
    unittest.main()
