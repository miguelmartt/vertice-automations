"""Every text this template sends, in English and Spanish. LANGUAGE=en|es in the config file."""

TEXTS = {
    "en": {
        "title_site": "📬 New contact from {site}",
        "title": "📬 New contact from your website",
        "message": "💬 Message:",
        "subject": "Subject: {subject}",
        "mailbox_down": "⚠️ Can't read the mailbox {user}: {error}\nForm alerts won't arrive until this is fixed.",
        "mailbox_back": "✅ Reading the mailbox {user} again.",
    },
    "es": {
        "title_site": "📬 Nuevo contacto de {site}",
        "title": "📬 Nuevo contacto desde tu web",
        "message": "💬 Mensaje:",
        "subject": "Asunto: {subject}",
        "mailbox_down": "⚠️ No puedo leer el buzón {user}: {error}\nLos avisos del formulario no llegarán hasta que se arregle.",
        "mailbox_back": "✅ Vuelvo a leer el buzón {user}.",
    },
}

_language = "en"


def set_language(code):
    global _language
    if code not in TEXTS:
        raise ValueError(f"LANGUAGE must be one of {', '.join(TEXTS)}, not {code!r}")
    _language = code


def t(key, **values):
    return TEXTS[_language][key].format(**values)
