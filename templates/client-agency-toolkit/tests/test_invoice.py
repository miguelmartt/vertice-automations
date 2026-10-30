import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import gotenberg  # noqa: E402
import invoice  # noqa: E402
import messages  # noqa: E402
from config import Config, ConfigError  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "..", "invoice.example.json")
PDF = b"%PDF-1.7 fake pdf"
EN, ES = messages.load("en"), messages.load("es")


def example(**changes):
    data = invoice.load(EXAMPLE)
    data.update(changes)
    return data


class Response(io.BytesIO):
    status = 200


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None, **kwargs):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


class TotalsTest(unittest.TestCase):
    def test_example(self):
        totals = invoice.compute(example())
        self.assertEqual([line["amount"] for line in totals["lines"]], [Decimal("500.00"), Decimal("150.00")])
        self.assertEqual(totals["subtotal"], Decimal("650.00"))
        self.assertEqual(totals["tax"], Decimal("136.50"))
        self.assertEqual(totals["total"], Decimal("786.50"))

    def test_decimal_and_rounding(self):
        totals = invoice.compute({"tax_rate": 21, "items": [
            {"desc": "a", "qty": 3, "price": 0.1},  # 0.30 exactly, no float noise
            {"desc": "b", "qty": 3, "price": "33.333"},  # 99.999 -> 100.00
            {"desc": "c", "qty": "1.5", "price": 0.07},  # 0.105 -> 0.11 (half up)
        ]})
        self.assertEqual([line["amount"] for line in totals["lines"]],
                         [Decimal("0.30"), Decimal("100.00"), Decimal("0.11")])
        self.assertEqual(totals["subtotal"], Decimal("100.41"))
        self.assertEqual(totals["tax"], Decimal("21.09"))  # 21.0861
        self.assertEqual(totals["total"], Decimal("121.50"))

    def test_vat_rounds_half_up(self):
        totals = invoice.compute({"tax_rate": 21, "items": [{"desc": "a", "qty": 1, "price": "0.50"}]})
        self.assertEqual(totals["tax"], Decimal("0.11"))  # 0.105, not 0.10

    def test_no_tax_rate(self):
        totals = invoice.compute({"items": [{"desc": "a", "qty": 2, "price": 10}]})
        self.assertEqual((totals["tax"], totals["total"]), (Decimal("0.00"), Decimal("20")))

    def test_bad_values(self):
        for items in (None, [], [{"desc": "a", "qty": "two", "price": 1}],
                      [{"desc": "a", "qty": True, "price": 1}], [{"desc": "a", "qty": 1}], ["a"]):
            with self.assertRaises(invoice.InvoiceError):
                invoice.compute({"items": items})


class RenderTest(unittest.TestCase):
    def test_spanish_look(self):
        page = invoice.render(example(), ES)
        for expected in ("<h1>FACTURA</h1>", "Nº 2026-001 · 30/10/2026", "Facturar a",
                         "<strong>Client Name</strong> · CLIENT_TAX_ID", "50,00 €", "650,00 €",
                         "IVA (21%)", "136,50 €", "786,50 €", "Pago a 30 días"):
            self.assertIn(expected, page)
        self.assertNotIn("$", page)  # Every placeholder was filled.

    def test_english(self):
        page = invoice.render(example(currency="USD", tax_rate=Decimal("10.5")), EN)
        for expected in ("<h1>INVOICE</h1>", "No. 2026-001 · 2026-10-30", "$650.00", "VAT (10.5%)", "$68.25"):
            self.assertIn(expected, page)

    def test_numbers_in_spanish(self):
        data = example(tax_rate=Decimal("10.5"), items=[{"desc": "Horas", "qty": Decimal("1.5"), "price": 10000}])
        page = invoice.render(data, ES)
        self.assertIn('<td class="r">1,5</td>', page)
        self.assertIn("15.000,00 €", page)
        self.assertIn("IVA (10,5%)", page)
        self.assertIn("1575,00 €", page)  # Spanish style: no separator in four-digit numbers.

    def test_everything_from_the_json_is_escaped(self):
        data = example(
            client_name='<script>alert("x")</script>',
            seller_address="Street & Sons <b>",
            invoice_number="2026-<001>",
            items=[{"desc": "Design & <i>code</i>", "qty": 1, "price": 10}],
        )
        page = invoice.render(data, EN)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", page)
        self.assertIn("Street &amp; Sons &lt;b&gt;", page)
        self.assertIn("No. 2026-&lt;001&gt;", page)
        self.assertIn("Design &amp; &lt;i&gt;code&lt;/i&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertNotIn("<i>", page)

    def test_required_fields(self):
        for key in ("invoice_number", "seller_name", "client_name"):
            with self.assertRaises(invoice.InvoiceError):
                invoice.render(example(**{key: ""}), EN)

    def test_bad_date(self):
        with self.assertRaises(invoice.InvoiceError):
            invoice.render(example(date="30/10/2026"), EN)

    def test_file_name(self):
        self.assertEqual(invoice.file_name(EN, "2026-001"), "invoice-2026-001.pdf")
        self.assertEqual(invoice.file_name(ES, "A/2026 01"), "factura-A-2026-01.pdf")


class GotenbergTest(unittest.TestCase):
    def test_multipart_body(self):
        body, content_type = gotenberg.multipart(
            {"printBackground": "true"},
            [("files", "index.html", "text/html; charset=utf-8", "<p>ñ</p>".encode())],
            "BOUNDARY",
        )
        self.assertEqual(content_type, "multipart/form-data; boundary=BOUNDARY")
        self.assertEqual(body, (
            b"--BOUNDARY\r\n"
            b'Content-Disposition: form-data; name="printBackground"\r\n'
            b"\r\n"
            b"true\r\n"
            b"--BOUNDARY\r\n"
            b'Content-Disposition: form-data; name="files"; filename="index.html"\r\n'
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<p>\xc3\xb1</p>\r\n"
            b"--BOUNDARY--\r\n"
        ))

    def test_request(self):
        with mock.patch("urllib.request.urlopen", return_value=Response(PDF)) as urlopen:
            pdf = gotenberg.html_to_pdf("http://localhost:3000/", "<p>hi</p>", boundary="B")
        self.assertEqual(pdf, PDF)
        req = urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://localhost:3000/forms/chromium/convert/html")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Content-type"), "multipart/form-data; boundary=B")
        self.assertIn(b'name="files"; filename="index.html"', req.data)
        self.assertIn(b'name="printBackground"\r\n\r\ntrue', req.data)
        self.assertIn(b'name="preferCssPageSize"\r\n\r\ntrue', req.data)
        self.assertTrue(req.data.endswith(b"--B--\r\n"))

    def test_errors(self):
        error = urllib.error.HTTPError("http://gotenberg", 400, "Bad", {}, io.BytesIO(b"no index.html"))
        for answer in (dict(side_effect=error), dict(return_value=Response(b"<html>not a pdf"))):
            with mock.patch("urllib.request.urlopen", **answer):
                with self.assertRaises(gotenberg.GotenbergError):
                    gotenberg.html_to_pdf("http://localhost:3000", "<p>hi</p>")


class CommandTest(unittest.TestCase):
    SETTINGS = Config(GOTENBERG_URL="http://localhost:3000", SMTP_HOST="smtp.example.com",
                      SMTP_FROM="billing@example.com", LANGUAGE="en")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.json = os.path.join(tmp.name, "invoice.json")
        shutil.copy(EXAMPLE, self.json)
        FakeSMTP.sent = []

    def run_invoice(self, settings, dry_run=False):
        with mock.patch("urllib.request.urlopen", return_value=Response(PDF)) as urlopen:
            with mock.patch("smtplib.SMTP", FakeSMTP):
                invoice.run(self.json, settings, dry_run)
        return urlopen

    def test_dry_run_writes_files_and_sends_nothing(self):
        self.run_invoice(self.SETTINGS, dry_run=True)
        stem = self.json[:-len(".json")]
        with open(stem + ".pdf", "rb") as f:
            self.assertEqual(f.read(), PDF)
        with open(stem + ".html", encoding="utf-8") as f:
            self.assertIn("INVOICE", f.read())
        self.assertEqual(FakeSMTP.sent, [])

    def test_dry_run_without_gotenberg_writes_the_html(self):
        with self.assertLogs("invoice", "WARNING"):
            urlopen = self.run_invoice(Config(), dry_run=True)
        self.assertTrue(os.path.exists(self.json[:-len(".json")] + ".html"))
        self.assertFalse(os.path.exists(self.json[:-len(".json")] + ".pdf"))
        urlopen.assert_not_called()

    def test_email_with_the_pdf(self):
        self.run_invoice(self.SETTINGS)
        (msg,) = FakeSMTP.sent
        self.assertEqual(msg["To"], "client@example.com")
        self.assertEqual(msg["From"], "billing@example.com")
        self.assertEqual(msg["Subject"], "Invoice 2026-001")
        self.assertIn("Hello Client Name", msg.get_body(("plain",)).get_content())
        (attachment,) = list(msg.iter_attachments())
        self.assertEqual(attachment.get_filename(), "invoice-2026-001.pdf")
        self.assertEqual(attachment.get_content_type(), "application/pdf")
        self.assertEqual(attachment.get_content(), PDF)

    def test_language_from_the_invoice(self):
        with open(EXAMPLE, encoding="utf-8") as f:
            data = json.load(f)
        with open(self.json, "w", encoding="utf-8") as f:
            json.dump(dict(data, language="es"), f)
        self.run_invoice(self.SETTINGS)
        self.assertEqual(FakeSMTP.sent[0]["Subject"], "Factura 2026-001")

    def test_off_when_not_configured(self):
        for settings in (Config(SMTP_HOST="smtp.example.com", SMTP_FROM="billing@example.com"),
                         Config(GOTENBERG_URL="http://localhost:3000")):
            with mock.patch("urllib.request.urlopen") as urlopen, mock.patch("smtplib.SMTP", FakeSMTP):
                with self.assertRaises(ConfigError):
                    invoice.run(self.json, settings)
            urlopen.assert_not_called()
        self.assertEqual(FakeSMTP.sent, [])

    def test_main_reports_errors(self):
        with mock.patch.object(invoice.config, "load", return_value=Config()), mock.patch("logging.basicConfig"):
            with self.assertLogs("invoice", "ERROR"):
                self.assertEqual(invoice.main([self.json]), 1)


if __name__ == "__main__":
    unittest.main()
