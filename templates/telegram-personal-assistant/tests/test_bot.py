import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import telegram  # noqa: E402
from bot import Bot, clean_url, find_url, route  # noqa: E402
from messages import Messages  # noqa: E402

CHAT = "YOUR_CHAT_ID"


class FakeStop:
    def __init__(self):
        self.flag = False
        self.waits = []

    def is_set(self):
        return self.flag

    def wait(self, seconds):
        self.waits.append(seconds)


class FakeTelegram:
    def __init__(self, batches=(), stop=None):
        self.sent = []
        self.calls = []
        self.offsets = []
        self.batches = list(batches)
        self.stop = stop

    def send_long(self, chat_id, text):
        self.sent.append((chat_id, text))

    def call(self, method, params=None):
        self.calls.append((method, params))

    def updates(self, offset, timeout=50, allowed=("message", "callback_query")):
        self.offsets.append(offset)
        if not self.batches:
            self.stop.flag = True
            return []
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        return batch


class FakeExpenses:
    def __init__(self):
        self.logged = []

    def log(self, text):
        self.logged.append(text)
        return "logged " + text if text[0].isdigit() else None

    def month(self):
        return "month summary"


class FakeReading:
    def __init__(self):
        self.saved = []

    def save(self, url):
        self.saved.append(url)
        return "saved " + url


class FakeStore(dict):
    def set(self, key, value):
        self[key] = value


def message(text, chat=CHAT, **extra):
    return {"chat": {"id": chat}, "text": text, **extra}


class RouteTest(unittest.TestCase):
    def test_month_commands(self):
        for text in ("/mes", "/month", "/MES", "/mes@my_assistant_bot", "/month please"):
            self.assertEqual(route(text), "month", text)

    def test_other_commands_get_help(self):
        for text in ("/start", "/help", "/mesa", "/foo bar"):
            self.assertEqual(route(text), "help", text)

    def test_a_command_wins_over_a_link(self):
        self.assertEqual(route("/mes https://example.com", "https://example.com"), "month")

    def test_link_wins_over_an_expense(self):
        self.assertEqual(route("12 read this https://example.com", "https://example.com"), "link")

    def test_plain_text_is_an_expense(self):
        self.assertEqual(route("12 lunch"), "expense")
        self.assertEqual(route("lunch"), "expense")

    def test_empty_message_gets_help(self):
        self.assertEqual(route(""), "help")


class FindUrlTest(unittest.TestCase):
    def test_first_link_in_the_text(self):
        msg = message("look at https://example.com/a?b=1 and https://example.org")
        self.assertEqual(find_url(msg), "https://example.com/a?b=1")

    def test_trailing_punctuation_is_dropped(self):
        self.assertEqual(find_url(message("(see https://example.com/post).")), "https://example.com/post")
        self.assertEqual(clean_url("https://example.com/wiki/Foo_(bar)"), "https://example.com/wiki/Foo_(bar)")

    def test_link_in_a_caption(self):
        self.assertEqual(find_url({"caption": "photo from http://example.com/x"}), "http://example.com/x")

    def test_link_hidden_behind_text(self):
        msg = message("an article", entities=[{"type": "bold"},
                                              {"type": "text_link", "url": "https://example.com/hidden"}])
        self.assertEqual(find_url(msg), "https://example.com/hidden")

    def test_no_link(self):
        self.assertIsNone(find_url(message("12 lunch at example.com")))
        self.assertIsNone(find_url(message("x", entities=[{"type": "text_link", "url": "tg://user?id=1"}])))


class BotTest(unittest.TestCase):
    def make(self, expenses=True, reading=True, daily=(), language="en"):
        self.tg = FakeTelegram()
        self.expenses = FakeExpenses() if expenses else None
        self.reading = FakeReading() if reading else None
        return Bot(self.tg, CHAT, Messages(language), self.expenses, self.reading, daily)

    def replies(self):
        return [text for _, text in self.tg.sent]

    def test_ignores_other_chats(self):
        bot = self.make()
        bot.handle(message("12 lunch", chat="SOMEONE_ELSE"))
        self.assertEqual(self.tg.sent, [])
        self.assertEqual(self.expenses.logged, [])

    def test_chat_id_can_be_a_number(self):
        bot = Bot(FakeTelegram(), -100, Messages(), FakeExpenses())
        bot.handle(message("12 lunch", chat=-100))
        self.assertEqual(bot.telegram.sent, [("-100", "logged 12 lunch")])

    def test_expense(self):
        bot = self.make()
        bot.handle(message("  12 lunch "))
        self.assertEqual(self.expenses.logged, ["12 lunch"])
        self.assertEqual(self.tg.sent, [(CHAT, "logged 12 lunch")])

    def test_link_goes_to_read_it_later_with_typing(self):
        bot = self.make()
        bot.handle(message("12 https://example.com/article"))
        self.assertEqual(self.reading.saved, ["https://example.com/article"])
        self.assertEqual(self.expenses.logged, [])
        self.assertEqual(self.tg.calls, [("sendChatAction", {"chat_id": CHAT, "action": "typing"})])
        self.assertEqual(self.replies(), ["saved https://example.com/article"])

    def test_month(self):
        bot = self.make()
        bot.handle(message("/mes"))
        self.assertEqual(self.replies(), ["month summary"])

    def test_unreadable_expense_hints_at_links(self):
        bot = self.make()
        bot.handle(message("lunch"))
        self.assertEqual(self.replies(), ["I couldn't read the amount. Write something like: 12 lunch\n"
                                          "Or send me a link and I'll save it with a summary."])

    def test_unreadable_expense_without_read_it_later(self):
        bot = self.make(reading=False, language="es")
        bot.handle(message("comida"))
        self.assertEqual(self.replies(), ["No he podido leer el importe. Escribe algo como: 12 comida"])

    def test_features_off(self):
        bot = self.make(expenses=False, reading=False)
        bot.handle(message("/month"))
        bot.handle(message("https://example.com"))
        self.assertIn("expense logger is not set up", self.replies()[0])
        self.assertIn("Read-it-later is not set up", self.replies()[1])

    def test_only_read_it_later_asks_for_a_link(self):
        bot = self.make(expenses=False, language="es")
        bot.handle(message("hola"))
        self.assertEqual(self.replies(), ["Mándame un enlace (http...) y te lo guardo con un resumen."])

    def test_help_lists_what_is_on(self):
        bot = self.make(reading=False, daily=[("calendar", "07:30"), ("email", "08:00")])
        bot.handle(message("/start"))
        reply = self.replies()[0]
        self.assertIn("/month", reply)
        self.assertNotIn("Read-it-later", reply)
        self.assertIn("Every day: today's agenda at 07:30, email digest at 08:00.", reply)

    def test_help_when_nothing_is_on(self):
        bot = self.make(expenses=False, reading=False)
        bot.handle(message("hello"))
        self.assertIn("Nothing is set up yet", self.replies()[0])

    def test_an_error_is_reported_and_the_bot_goes_on(self):
        bot = self.make()

        def broken(text):
            raise RuntimeError("Sheets is down")

        self.expenses.log = broken
        with self.assertLogs("bot", "ERROR"):
            bot.handle(message("12 lunch"))
        self.assertEqual(self.replies(), ["Something went wrong: Sheets is down"])


class PollTest(unittest.TestCase):
    def test_saves_the_offset_and_resumes_from_it(self):
        stop = FakeStop()
        updates = [
            {"update_id": 7, "message": message("12 lunch")},
            {"update_id": 8, "edited_message": message("13 lunch")},
            {"update_id": 9, "message": message("12 taxi", chat="SOMEONE_ELSE")},
        ]
        tg = FakeTelegram([updates], stop)
        store = FakeStore(telegram_offset=7)
        expenses = FakeExpenses()
        Bot(tg, CHAT, Messages(), expenses, store=store).poll(stop)
        self.assertEqual(tg.offsets, [7, 10])
        self.assertEqual(store["telegram_offset"], 10)
        self.assertEqual(expenses.logged, ["12 lunch"])

    def test_telegram_errors_wait_and_retry(self):
        stop = FakeStop()
        tg = FakeTelegram([telegram.TelegramError("getUpdates: timed out")], stop)
        with self.assertLogs("bot", "WARNING"):
            Bot(tg, CHAT, Messages()).poll(stop)
        self.assertEqual(stop.waits, [15])
        self.assertEqual(tg.offsets, [0, 0])


if __name__ == "__main__":
    unittest.main()
