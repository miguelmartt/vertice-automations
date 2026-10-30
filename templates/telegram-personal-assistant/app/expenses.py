"""Expense logger: "12 lunch" becomes a row in the Expenses tab; /month (or /mes) sums the month by category.

Tab layout, first row as header: Date | Amount | Currency | Category | Note (columns A to E).
"""

import re
from collections import namedtuple

# The first number in the message, with an optional currency before or after it: 12, 12,50, 12.5€,
# 12 eur, $12...
AMOUNT = re.compile(r"(?:(€|\$)\s*)?(\d+(?:[.,]\d+)?)\s*(€|\$|(?:euros?|eur|usd)\b)?", re.IGNORECASE)
CURRENCIES = {"€": "€", "eur": "€", "euro": "€", "euros": "€", "$": "$", "usd": "$"}

Expense = namedtuple("Expense", "date amount currency category note")


def parse(text, day, currency, uncategorized):
    """"12 lunch", "12€ lunch", "lunch 12,50"... -> Expense, or None if there is no amount.

    Whatever is not the amount is the note, and its first word (lowercase) the category.
    day is the date to log (YYYY-MM-DD), currency the one used when the message names none.
    """
    match = AMOUNT.search(text)
    if not match:
        return None
    symbol, number, word = match.groups()
    amount = float(number.replace(",", "."))
    if word or symbol:
        currency = CURRENCIES[(word or symbol).lower()]
    rest = text[:match.start()] + " " + text[match.end():]
    note = " ".join(rest.replace("€", " ").replace("$", " ").split())
    category = note.split()[0].strip(".,;:!?").lower() if note else ""
    return Expense(day, amount, currency, category or uncategorized, note or uncategorized)


def show(amount):
    """12.0 -> "12", 12.5 -> "12.5"."""
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _number(value):
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


def _cell(row, i):
    return str(row[i]).strip() if i < len(row) else ""  # Sheets leaves out empty cells at the end


def month_summary(rows, month, t, currency):
    """Total and per-category sums of the rows whose date starts with month (YYYY-MM).

    The header row never matches, so it does not need to be skipped.
    """
    mine = [row for row in rows if _cell(row, 0).startswith(month)]
    if not mine:
        return t("month_empty", month=month)
    total = 0.0
    by_category = {}
    for row in mine:
        amount = _number(row[1]) if len(row) > 1 else 0.0
        category = _cell(row, 3) or t("other_category")
        total += amount
        by_category[category] = by_category.get(category, 0.0) + amount
    currency = _cell(mine[0], 2) or currency
    lines = [f"• {c}: {v:.2f}{currency}"
             for c, v in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)]
    head = t("month_summary", month=month, total=f"{total:.2f}", currency=currency, count=len(mine))
    return head + "\n\n" + "\n".join(lines)


class Expenses:
    def __init__(self, sheets, sheet, t, now, currency="€"):
        self.sheets = sheets
        self.sheet = sheet
        self.t = t
        self.now = now
        self.currency = currency

    def log(self, text):
        """Saves the expense and returns the confirmation, or None if the text has no amount."""
        expense = parse(text, self.now().strftime("%Y-%m-%d"), self.currency, self.t("uncategorized"))
        if expense is None:
            return None
        self.sheets.append(self.sheet, list(expense))
        return self.t("expense_saved", amount=show(expense.amount), currency=expense.currency,
                      note=expense.note)

    def month(self):
        return month_summary(self.sheets.rows(self.sheet), self.now().strftime("%Y-%m"), self.t, self.currency)
