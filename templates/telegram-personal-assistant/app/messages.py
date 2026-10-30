"""Every text the user reads, in English and Spanish (Spain). Pick one with LANGUAGE=en or es."""

from config import ConfigError

TEXTS = {
    "en": {
        # Used in the Gemini prompts: "Write it in ...".
        "language_name": "English",
        "date_format": "%Y-%m-%d",

        "help_title": "🤖 Your personal assistant. This is what I can do:",
        "help_expenses": "• Log an expense: send \"12 lunch\", \"12€ taxi\" or \"lunch 12,50\".\n"
                         "• /month: this month's expenses by category.",
        "help_reading": "• Read-it-later: send me a link and I save it with a summary.",
        "help_daily": "• Every day: {items}.",
        "help_email": "email digest at {time}",
        "help_calendar": "today's agenda at {time}",
        "help_news": "news digest at {time}",
        "help_nothing": "Nothing is set up yet: fill in the config file and restart the service.",

        "job_email": "email digest",
        "job_calendar": "calendar agenda",
        "job_news": "news digest",
        "job_failed": "⚠️ The {job} failed: {error}\nI'll tell you when it works again.",
        "job_recovered": "✅ The {job} works again.",
        "error": "Something went wrong: {error}",

        "email_title": "📬 Email digest",
        "email_none": "📬 No new email in the last 24 hours.",
        "news_title": "📰 News digest",
        "news_none": "📰 Nothing new in your feeds today.",

        "agenda_title": "🗓️ Today's agenda ({date})",
        "agenda_empty": "No events today. Free day. 🎉",
        "agenda_count": "You have {count} event(s):",
        "agenda_all_day": "(all day)",
        "agenda_gaps": "🟢 Free slots ({start}–{end}): {gaps}",
        "no_title": "(no title)",

        "expense_saved": "💸 Logged: {amount}{currency} · {note}",
        "expense_unreadable": "I couldn't read the amount. Write something like: 12 lunch",
        "link_hint": "Or send me a link and I'll save it with a summary.",
        "uncategorized": "(uncategorized)",
        "other_category": "(other)",
        "month_empty": "📊 {month}: no expenses logged this month yet.",
        "month_summary": "📊 Expenses for {month}\nTotal: {total}{currency} in {count} entries",
        "off_expenses": "The expense logger is not set up (it needs the Google settings and SPREADSHEET_ID).",

        "reading_saved": "📑 Saved: {title}\n\n{summary}",
        "reading_unreadable": "I couldn't read this page (it may need JavaScript or block bots), "
                              "but I saved the link anyway.",
        "reading_send_link": "Send me a link (http...) and I'll save it with a summary.",
        "off_reading": "Read-it-later is not set up (it needs the Google settings, SPREADSHEET_ID and "
                       "GEMINI_API_KEY).",
    },
    "es": {
        "language_name": "Spanish (Spain)",
        "date_format": "%d/%m/%Y",

        "help_title": "🤖 Tu asistente personal. Esto es lo que sé hacer:",
        "help_expenses": "• Apuntar un gasto: escribe «12 comida», «12€ taxi» o «comida 12,50».\n"
                         "• /mes: los gastos de este mes por categoría.",
        "help_reading": "• Guardar para leer: mándame un enlace y te lo guardo con un resumen.",
        "help_daily": "• Cada día: {items}.",
        "help_email": "resumen del correo a las {time}",
        "help_calendar": "agenda del día a las {time}",
        "help_news": "resumen de noticias a las {time}",
        "help_nothing": "Todavía no hay nada configurado: rellena el fichero de configuración y reinicia "
                        "el servicio.",

        "job_email": "el resumen del correo",
        "job_calendar": "la agenda del día",
        "job_news": "el resumen de noticias",
        "job_failed": "⚠️ Ha fallado {job}: {error}\nTe aviso cuando vuelva a funcionar.",
        "job_recovered": "✅ Vuelve a funcionar {job}.",
        "error": "Algo ha fallado: {error}",

        "email_title": "📬 Resumen del correo",
        "email_none": "📬 No hay correo nuevo en las últimas 24 horas.",
        "news_title": "📰 Resumen de noticias",
        "news_none": "📰 Hoy no hay nada nuevo en tus feeds.",

        "agenda_title": "🗓️ Agenda de hoy ({date})",
        "agenda_empty": "No tienes eventos hoy. Día libre. 🎉",
        "agenda_count": "Tienes {count} evento(s):",
        "agenda_all_day": "(todo el día)",
        "agenda_gaps": "🟢 Huecos libres ({start}–{end}): {gaps}",
        "no_title": "(sin título)",

        "expense_saved": "💸 Registrado: {amount}{currency} · {note}",
        "expense_unreadable": "No he podido leer el importe. Escribe algo como: 12 comida",
        "link_hint": "O mándame un enlace y te lo guardo con un resumen.",
        "uncategorized": "(sin categoría)",
        "other_category": "(otros)",
        "month_empty": "📊 {month}: aún no hay gastos registrados este mes.",
        "month_summary": "📊 Gastos de {month}\nTotal: {total}{currency} en {count} apuntes",
        "off_expenses": "El registro de gastos no está configurado (necesita los datos de Google y "
                        "SPREADSHEET_ID).",

        "reading_saved": "📑 Guardado: {title}\n\n{summary}",
        "reading_unreadable": "No he podido leer esta página (puede que necesite JavaScript o que bloquee "
                              "bots), pero te guardo el enlace igualmente.",
        "reading_send_link": "Mándame un enlace (http...) y te lo guardo con un resumen.",
        "off_reading": "Guardar para leer no está configurado (necesita los datos de Google, SPREADSHEET_ID "
                       "y GEMINI_API_KEY).",
    },
}


class Messages:
    """t = Messages("es"); t("expense_saved", amount="12", currency="€", note="comida")."""

    def __init__(self, language="en"):
        if language not in TEXTS:
            raise ConfigError(f"LANGUAGE must be one of {', '.join(TEXTS)}, not {language!r}")
        self.language = language
        self.texts = TEXTS[language]

    def __call__(self, key, **values):
        return self.texts[key].format(**values)
