"""Every text a person reads (Telegram alerts, emails, the invoice), in English and Spanish.

LANGUAGE=en or es in the config file; English by default. Number, money and date formats too.
"""

from decimal import ROUND_HALF_UP, Decimal

from config import ConfigError

TEXTS = {
    "en": {
        "lang": "en",
        # Uptime alerts (Telegram).
        "site_down": "⛔ {label} is down: HTTP {status}\n{url}",
        "site_unreachable": "⛔ {label} is not responding ({reason})\n{url}",
        "site_warning": "⚠️ {label} responds with HTTP {status}\n{url}",
        "site_recovered": "✅ {label} is back up (HTTP {status})\n{url}",
        # A scheduled job that starts failing or works again (Telegram).
        "job_failed": "⚠️ Agency toolkit: the {job} is failing.\n{error}",
        "job_recovered": "✅ Agency toolkit: the {job} works again.",
        "job_uptime": "uptime monitor",
        "job_report": "weekly report",
        # Weekly analytics report (email).
        "report_subject": "Weekly report — {site}",
        "report_title": "Weekly report · {site}",
        "report_period": "Period: {start} – {end}",
        "visitors": "Visitors",
        "pageviews": "Pageviews",
        "bounce_rate": "Bounce rate",
        "visit_duration": "Avg. visit duration",
        "top_pages": "Top pages",
        "page": "Page",
        "top_sources": "Traffic sources",
        "source": "Source",
        "no_data": "No data",
        "direct": "(direct)",
        "report_footer": "Generated with {provider} data.",
        # Invoice (PDF and email).
        "invoice_title": "INVOICE",
        "invoice_number": "No. {number} · {date}",
        "bill_to": "Bill to",
        "col_item": "Description",
        "col_qty": "Qty",
        "col_price": "Price",
        "col_amount": "Amount",
        "subtotal": "Subtotal",
        "tax": "VAT ({rate}%)",
        "total": "Total",
        "invoice_footer": "Thank you for your business. Payment due within 30 days unless otherwise agreed.",
        "invoice_subject": "Invoice {number}",
        "invoice_body": "Hello {client},\n\nPlease find attached invoice {number}.\n\nBest regards.",
        "invoice_file": "invoice-{number}.pdf",
        # Formats.
        "date_format": "%Y-%m-%d",
        "decimal": ".",
        "thousands": ",",
        "group_from": 4,
        "currency_after": False,
    },
    "es": {
        "lang": "es",
        "site_down": "⛔ {label} caído: HTTP {status}\n{url}",
        "site_unreachable": "⛔ {label} no responde ({reason})\n{url}",
        "site_warning": "⚠️ {label} responde HTTP {status}\n{url}",
        "site_recovered": "✅ {label} vuelve a funcionar (HTTP {status})\n{url}",
        "job_failed": "⚠️ Agency toolkit: falla el {job}.\n{error}",
        "job_recovered": "✅ Agency toolkit: el {job} vuelve a funcionar.",
        "job_uptime": "monitor de uptime",
        "job_report": "informe semanal",
        "report_subject": "Informe semanal — {site}",
        "report_title": "Informe semanal · {site}",
        "report_period": "Periodo: del {start} al {end}",
        "visitors": "Visitantes",
        "pageviews": "Páginas vistas",
        "bounce_rate": "Rebote",
        "visit_duration": "Duración media",
        "top_pages": "Páginas más vistas",
        "page": "Página",
        "top_sources": "Fuentes de tráfico",
        "source": "Fuente",
        "no_data": "Sin datos",
        "direct": "(directo)",
        "report_footer": "Generado con datos de {provider}.",
        "invoice_title": "FACTURA",
        "invoice_number": "Nº {number} · {date}",
        "bill_to": "Facturar a",
        "col_item": "Concepto",
        "col_qty": "Cant.",
        "col_price": "Precio",
        "col_amount": "Importe",
        "subtotal": "Subtotal",
        "tax": "IVA ({rate}%)",
        "total": "Total",
        "invoice_footer": "Gracias por su confianza. Pago a 30 días salvo acuerdo.",
        "invoice_subject": "Factura {number}",
        "invoice_body": "Hola {client},\n\nAdjuntamos la factura {number}.\n\nUn saludo.",
        "invoice_file": "factura-{number}.pdf",
        "date_format": "%d/%m/%Y",
        "decimal": ",",
        "thousands": ".",
        "group_from": 5,  # Spanish style: 1234 but 12.345
        "currency_after": True,
    },
}

SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}


def load(language):
    """The texts for a LANGUAGE value (en or es)."""
    texts = TEXTS.get((language or "en").strip().lower())
    if texts is None:
        raise ConfigError(f"LANGUAGE must be one of {', '.join(TEXTS)}, not {language!r}")
    return texts


def number(value, texts, places=0):
    """A number with the separators of the language: 12,345.60 in English, 12.345,60 in Spanish."""
    value = Decimal(value).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
    text = format(value, f".{places}f")
    sign = "-" if text.startswith("-") else ""
    whole, _, fraction = text.lstrip("-").partition(".")
    if len(whole) >= texts["group_from"]:
        whole = f"{int(whole):,}".replace(",", texts["thousands"])
    return sign + whole + (texts["decimal"] + fraction if fraction else "")


def money(value, currency, texts):
    """An amount with its currency: €1,234.50 in English, 1234,50 € in Spanish."""
    code = (currency or "EUR").strip().upper()
    symbol = SYMBOLS.get(code)
    amount = number(value, texts, 2)
    if texts["currency_after"]:
        return f"{amount} {symbol or code}"
    return f"{symbol}{amount}" if symbol else f"{code} {amount}"
