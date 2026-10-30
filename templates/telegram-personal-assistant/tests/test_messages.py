import os
import string
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import config  # noqa: E402
import messages  # noqa: E402


def fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


class MessagesTest(unittest.TestCase):
    def test_both_languages_have_the_same_texts_and_placeholders(self):
        en, es = messages.TEXTS["en"], messages.TEXTS["es"]
        self.assertEqual(set(en), set(es))
        for key in en:
            self.assertEqual(fields(en[key]), fields(es[key]), key)

    def test_default_is_english(self):
        self.assertEqual(messages.Messages()("error", error="x"), "Something went wrong: x")

    def test_spanish(self):
        self.assertEqual(messages.Messages("es")("error", error="x"), "Algo ha fallado: x")

    def test_unknown_language(self):
        with self.assertRaises(config.ConfigError):
            messages.Messages("fr")


if __name__ == "__main__":
    unittest.main()
