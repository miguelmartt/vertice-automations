import tempfile
import unittest

import config
import messages
import vertiguard


def cfg(**values):
    c = config.Config({"TELEGRAM_CHAT_ID": "42", "ALERTS_BOT_TOKEN": "x", "STATE_DIR": tempfile.mkdtemp()})
    c.update(values)
    return c


class BuildTest(unittest.TestCase):
    def tearDown(self):
        messages.set_language("en")

    def test_only_alerts_by_default(self):
        parts, webhook = vertiguard.build(cfg())
        self.assertEqual(list(parts), ["alerts"])
        self.assertIsNone(webhook)

    def test_bot_and_webhook_when_configured(self):
        parts, webhook = vertiguard.build(cfg(DEVOPS_BOT_TOKEN="y", WEBHOOK_PORT="0", LANGUAGE="es"))
        try:
            self.assertEqual(list(parts), ["alerts", "bot", "uptimerobot"])
            self.assertEqual(messages.t("cancelled"), "Cancelado.")
        finally:
            webhook.server_close()

    def test_missing_chat_id(self):
        c = cfg()
        del c["TELEGRAM_CHAT_ID"]
        with self.assertRaises(config.ConfigError):
            vertiguard.build(c)


if __name__ == "__main__":
    unittest.main()
