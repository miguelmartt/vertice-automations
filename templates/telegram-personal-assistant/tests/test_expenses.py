import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from expenses import Expenses, month_summary, parse, show  # noqa: E402
from messages import Messages  # noqa: E402

DAY = "2026-10-30"
NOW = datetime(2026, 10, 30, 23, 30, tzinfo=timezone(timedelta(hours=1)))


def amount(text, currency="€"):
    expense = parse(text, DAY, currency, "(uncategorized)")
    return (expense.amount, expense.currency, expense.category, expense.note)


class FakeSheets:
    def __init__(self, rows=()):
        self.appended = []
        self._rows = list(rows)

    def append(self, sheet, row):
        self.appended.append((sheet, row))

    def rows(self, sheet):
        return self._rows


class ParseTest(unittest.TestCase):
    def test_the_examples_of_the_old_workflow(self):
        self.assertEqual(amount("12 lunch"), (12.0, "€", "lunch", "lunch"))
        self.assertEqual(amount("12€ lunch"), (12.0, "€", "lunch", "lunch"))
        self.assertEqual(amount("lunch 12,50"), (12.5, "€", "lunch", "lunch"))

    def test_currency_words_and_symbols(self):
        self.assertEqual(amount("12 euros comida"), (12.0, "€", "comida", "comida"))
        self.assertEqual(amount("12 EUR comida"), (12.0, "€", "comida", "comida"))
        self.assertEqual(amount("15 usd taxi"), (15.0, "$", "taxi", "taxi"))
        self.assertEqual(amount("taxi 15$"), (15.0, "$", "taxi", "taxi"))
        self.assertEqual(amount("$12.5 taxi"), (12.5, "$", "taxi", "taxi"))

    def test_a_word_that_starts_like_a_currency_is_not_one(self):
        self.assertEqual(amount("12 eurovision tickets"), (12.0, "€", "eurovision", "eurovision tickets"))

    def test_default_currency(self):
        self.assertEqual(amount("12 lunch", currency="$"), (12.0, "$", "lunch", "lunch"))

    def test_category_is_the_first_word_lowercase(self):
        self.assertEqual(amount("Groceries, weekly shop 54.20"),
                         (54.2, "€", "groceries", "Groceries, weekly shop"))

    def test_no_description(self):
        self.assertEqual(amount("12"), (12.0, "€", "(uncategorized)", "(uncategorized)"))

    def test_no_amount(self):
        self.assertIsNone(parse("lunch", DAY, "€", "-"))
        self.assertIsNone(parse("", DAY, "€", "-"))

    def test_the_date_is_kept(self):
        self.assertEqual(parse("12 lunch", DAY, "€", "-").date, DAY)

    def test_show(self):
        self.assertEqual(show(12.0), "12")
        self.assertEqual(show(12.5), "12.5")
        self.assertEqual(show(12.25), "12.25")


class MonthSummaryTest(unittest.TestCase):
    ROWS = [
        ["Date", "Amount", "Currency", "Category", "Note"],
        ["2026-09-30", 100, "€", "rent", "rent"],
        ["2026-10-01", 12.5, "€", "lunch", "lunch"],
        ["2026-10-02", "7,50", "€", "taxi", "taxi"],
        ["2026-10-03", 20, "€", "lunch", "lunch with friends"],
        ["2026-10-04", 3],  # Sheets leaves out empty cells at the end
    ]

    def test_totals_by_category_sorted(self):
        text = month_summary(self.ROWS, "2026-10", Messages("es"), "€")
        self.assertEqual(text, "📊 Gastos de 2026-10\nTotal: 43.00€ en 4 apuntes\n\n"
                               "• lunch: 32.50€\n• taxi: 7.50€\n• (otros): 3.00€")

    def test_empty_month(self):
        self.assertEqual(month_summary(self.ROWS, "2026-11", Messages("en"), "€"),
                         "📊 2026-11: no expenses logged this month yet.")


class ExpensesTest(unittest.TestCase):
    def test_log_appends_the_row_in_column_order(self):
        sheets = FakeSheets()
        reply = Expenses(sheets, "Expenses", Messages("es"), lambda: NOW).log("12,50€ comida en el centro")
        self.assertEqual(sheets.appended, [("Expenses", ["2026-10-30", 12.5, "€", "comida", "comida en el centro"])])
        self.assertEqual(reply, "💸 Registrado: 12.5€ · comida en el centro")

    def test_log_without_amount_saves_nothing(self):
        sheets = FakeSheets()
        self.assertIsNone(Expenses(sheets, "Expenses", Messages(), lambda: NOW).log("lunch"))
        self.assertEqual(sheets.appended, [])

    def test_month_uses_the_local_month(self):
        sheets = FakeSheets([["2026-10-30", 5, "$", "coffee", "coffee"]])
        text = Expenses(sheets, "Expenses", Messages(), lambda: NOW, currency="$").month()
        self.assertTrue(text.startswith("📊 Expenses for 2026-10\nTotal: 5.00$ in 1 entries"))


if __name__ == "__main__":
    unittest.main()
