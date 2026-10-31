"""Every text this template sends, in English and Spanish. LANGUAGE=en|es in the config file."""

TEXTS = {
    "en": {
        "title_site": "📬 New contact from {site}",
        "title": "📬 New contact from your website",
        "message": "💬 Message:",
        "subject": "Subject: {subject}",
        "mailbox_down": "⚠️ Can't read the mailbox {user}: {error}\nForm alerts won't arrive until this is fixed.",
        "mailbox_back": "✅ Reading the mailbox {user} again.",
        "failed": "⚠️ A form email could not be forwarded.\nSubject: {subject}\nRead it in the mailbox.",
        "too_big": "⚠️ A form email is too big to forward ({size} MB).\nSubject: {subject}\nRead it in the mailbox.",
        "not_from_site": "⚠️ Not forwarded: {n} email(s) with the form subject that do not come from your website "
                         "(FORM_FROM or DKIM check). They are still in the mailbox.",
    },
    "es": {
        "title_site": "📬 Nuevo contacto de {site}",
        "title": "📬 Nuevo contacto desde tu web",
        "message": "💬 Mensaje:",
        "subject": "Asunto: {subject}",
        "mailbox_down": "⚠️ No puedo leer el buzón {user}: {error}\nLos avisos del formulario no llegarán hasta que se arregle.",
        "mailbox_back": "✅ Vuelvo a leer el buzón {user}.",
        "failed": "⚠️ No he podido reenviar un correo del formulario.\nAsunto: {subject}\nLéelo en el buzón.",
        "too_big": "⚠️ Un correo del formulario es demasiado grande para reenviarlo ({size} MB).\nAsunto: {subject}\n"
                   "Léelo en el buzón.",
        "not_from_site": "⚠️ Sin reenviar: {n} correo(s) con el asunto del formulario que no vienen de tu web "
                         "(comprobación de FORM_FROM o DKIM). Siguen en el buzón.",
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
