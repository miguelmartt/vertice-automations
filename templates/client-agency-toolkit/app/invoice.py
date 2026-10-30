"""Invoice generator: invoice data (JSON) -> HTML -> PDF (Gotenberg) -> email to the client.

Usage:
  python3 invoice.py invoice.json [--dry-run] [--config /etc/agency-toolkit/agency-toolkit.env]

--dry-run writes invoice.html and invoice.pdf next to the JSON file and sends nothing.
See invoice.example.json for the fields.
"""

import argparse
import html
import json
import logging
import os
import re
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from string import Template

import config
import gotenberg
import mailer
import messages

log = logging.getLogger("invoice")

DEFAULT_CONFIG = "/etc/agency-toolkit/agency-toolkit.env"
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "invoice_template.html")
CENT = Decimal("0.01")


class InvoiceError(Exception):
    pass


def missing_settings(settings):
    return [] if settings.get_str("GOTENBERG_URL") else ["GOTENBERG_URL"]


def load(path):
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f, parse_float=Decimal)
        except ValueError as e:
            raise InvoiceError(f"{path} is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise InvoiceError(f"{path} must hold a JSON object")
    return data


def text(data, key, required=False):
    value = str(data.get(key) or "").strip()
    if required and not value:
        raise InvoiceError(f"{key} is missing from the invoice data")
    return value


def amount(value, field):
    if value is None or isinstance(value, bool):
        raise InvoiceError(f"{field} must be a number")
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation:
        raise InvoiceError(f"{field} must be a number, not {value!r}") from None
    if not result.is_finite():
        raise InvoiceError(f"{field} must be a number, not {value!r}")
    return result


def compute(data):
    """Each line rounded to cents, then VAT on the subtotal (half up), then the total."""
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise InvoiceError("items must be a list with at least one line")
    lines = []
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise InvoiceError(f"items[{n}] must be an object with desc, qty and price")
        qty = amount(item.get("qty"), f"items[{n}].qty")
        price = amount(item.get("price"), f"items[{n}].price")
        lines.append({
            "desc": text(item, "desc"),
            "qty": qty,
            "price": price,
            "amount": (qty * price).quantize(CENT, ROUND_HALF_UP),
        })
    subtotal = sum((line["amount"] for line in lines), Decimal("0"))
    rate = amount(data.get("tax_rate", 0), "tax_rate")
    tax = (subtotal * rate / 100).quantize(CENT, ROUND_HALF_UP)
    return {"lines": lines, "subtotal": subtotal, "tax_rate": rate, "tax": tax, "total": subtotal + tax}


def plain(value, texts):
    """A quantity or rate as written: 10, 1.5 (1,5 in Spanish), 21."""
    places = max(0, -value.normalize().as_tuple().exponent)
    return messages.number(value, texts, places)


def invoice_date(data):
    value = text(data, "date")
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InvoiceError(f"date must look like 2026-01-31, not {value!r}") from None


def render(data, texts):
    """The invoice as an HTML page. Every value from the JSON is escaped."""
    totals = compute(data)
    currency = text(data, "currency") or "EUR"
    esc = html.escape

    def money(value):
        return esc(messages.money(value, currency, texts))

    rows = "".join(
        f'<tr><td>{esc(line["desc"])}</td><td class="r">{esc(plain(line["qty"], texts))}</td>'
        f'<td class="r">{money(line["price"])}</td><td class="r">{money(line["amount"])}</td></tr>'
        for line in totals["lines"]
    )
    number = text(data, "invoice_number", required=True)
    client_taxid = text(data, "client_taxid")
    values = {
        "lang": texts["lang"],
        "title": texts["invoice_title"],
        "number": number,
        "number_line": texts["invoice_number"].format(
            number=number, date=invoice_date(data).strftime(texts["date_format"])
        ),
        "seller_name": text(data, "seller_name", required=True),
        "seller_taxid": text(data, "seller_taxid"),
        "seller_address": text(data, "seller_address"),
        "bill_to": texts["bill_to"],
        "client_name": text(data, "client_name", required=True),
        "client_taxid": f" · {client_taxid}" if client_taxid else "",
        "client_email": text(data, "client_email"),
        "col_item": texts["col_item"],
        "col_qty": texts["col_qty"],
        "col_price": texts["col_price"],
        "col_amount": texts["col_amount"],
        "subtotal_label": texts["subtotal"],
        "subtotal": messages.money(totals["subtotal"], currency, texts),
        "tax_label": texts["tax"].format(rate=plain(totals["tax_rate"], texts)),
        "tax": messages.money(totals["tax"], currency, texts),
        "total_label": texts["total"],
        "total": messages.money(totals["total"], currency, texts),
        "footer": texts["invoice_footer"],
    }
    values = {key: esc(value) for key, value in values.items()}
    values["rows"] = rows
    with open(TEMPLATE, encoding="utf-8") as f:
        return Template(f.read()).substitute(values)


def file_name(texts, number):
    return texts["invoice_file"].format(number=re.sub(r"[^A-Za-z0-9._-]+", "-", number).strip("-") or "invoice")


def email(settings, data, texts, pdf):
    number = text(data, "invoice_number", required=True)
    client = text(data, "client_name", required=True)
    mailer.send(
        settings,
        [text(data, "client_email", required=True)],
        texts["invoice_subject"].format(number=number),
        texts["invoice_body"].format(client=client, number=number),
        attachments=[(file_name(texts, number), pdf, "application/pdf")],
    )


def run(path, settings, dry_run=False):
    data = load(path)
    texts = messages.load(text(data, "language") or settings.get_str("LANGUAGE", "en"))
    page = render(data, texts)
    gotenberg_url = settings.get_str("GOTENBERG_URL")

    if dry_run:
        stem = os.path.splitext(path)[0]
        with open(stem + ".html", "w", encoding="utf-8") as f:
            f.write(page)
        log.info("Wrote %s.html", stem)
        if not gotenberg_url:
            log.warning("GOTENBERG_URL is not set: no PDF")
            return
        with open(stem + ".pdf", "wb") as f:
            f.write(gotenberg.html_to_pdf(gotenberg_url, page))
        log.info("Wrote %s.pdf (dry run: nothing sent)", stem)
        return

    missing = missing_settings(settings) + mailer.missing_settings(settings)
    if missing:
        raise config.ConfigError(f"Invoices are off: set {', '.join(missing)} in the config file")
    text(data, "client_email", required=True)  # Fail before rendering the PDF.
    email(settings, data, texts, gotenberg.html_to_pdf(gotenberg_url, page))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Invoice data (JSON) -> PDF -> email to the client.")
    parser.add_argument("invoice", help="the invoice data, a JSON file like invoice.example.json")
    parser.add_argument("--dry-run", action="store_true", help="write the HTML and PDF next to the JSON, send nothing")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config file (default {DEFAULT_CONFIG})")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        run(args.invoice, config.load(args.config), args.dry_run)
    except (OSError, config.ConfigError, InvoiceError, gotenberg.GotenbergError) as e:  # SMTP errors are OSErrors
        log.error("%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
