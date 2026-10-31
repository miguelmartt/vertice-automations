import tempfile
import unittest

import config
import messages
import vertiguard


def cfg(**values):
    c = config.Config({"TELEGRAM_CHAT_ID": "42", "BOT_TOKEN": "123:TEST", "STATE_DIR": tempfile.mkdtemp()})
    c.update(values)
    return c


class BuildTest(unittest.TestCase):
    def tearDown(self):
        messages.set_language("en")

    def test_alerts_and_commands_by_default(self):
        parts, webhook = vertiguard.build(cfg())
        self.assertEqual(list(parts), ["alerts", "bot"])
        self.assertIsNone(webhook)

    def test_commands_off(self):
        parts, _ = vertiguard.build(cfg(COMMANDS="off", REPORT_HOUR="off"))
        self.assertEqual(list(parts), ["alerts"])

    def test_first_release_token_name_still_works(self):
        c = cfg()
        c["ALERTS_BOT_TOKEN"] = c.pop("BOT_TOKEN")
        self.assertIn("alerts", vertiguard.build(c)[0])

    def test_bot_and_webhook_when_configured(self):
        parts, webhook = vertiguard.build(cfg(WEBHOOK_PORT="0", LANGUAGE="es"))
        try:
            self.assertEqual(list(parts), ["alerts", "bot", "uptimerobot"])
            self.assertEqual(messages.t("btn_cancel"), "✖️ Cancelar")
        finally:
            webhook.server_close()

    def test_missing_chat_id_or_token(self):
        c = cfg()
        del c["TELEGRAM_CHAT_ID"]
        with self.assertRaises(config.ConfigError):
            vertiguard.build(c)
        c = cfg()
        del c["BOT_TOKEN"]
        with self.assertRaises(config.ConfigError):
            vertiguard.build(c)


if __name__ == "__main__":
    unittest.main()
