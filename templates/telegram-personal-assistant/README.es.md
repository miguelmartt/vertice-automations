# Asistente personal por Telegram (n8n + Gemini)

Una pequeña familia de workflows de **n8n** que convierten un bot de Telegram en un asistente
personal: **resumen de email** por la mañana, **agenda del día**, **digest de noticias/RSS** con IA,
**registro de gastos** y **guardar-para-leer** que resume cualquier enlace que le mandes. La IA usa
**Google Gemini** (capa gratis); gastos y enlaces guardados van a **Google Sheets**.

> 🇬🇧 [English version](README.md)

Cada workflow es independiente — importa solo los que quieras. Todos salen **inactivos**
(`"active": false`): nada se ejecuta hasta que lo revisas.

---

## Qué incluye

| Fichero | Qué hace | Disparador | Stack |
|---|---|---|---|
| [`workflows/a15-email-daily-digest.json`](workflows/a15-email-daily-digest.json) | Cada mañana resume el correo de las últimas 24h en un digest de Telegram agrupado por *necesita respuesta / FYI / ruido*. | Schedule (08:00) | Gmail · Gemini · Telegram |
| [`workflows/a16-calendar-daily-digest.json`](workflows/a16-calendar-daily-digest.json) | Manda la agenda de hoy y tus huecos libres en horario laboral. | Schedule (07:30) | Google Calendar · Telegram |
| [`workflows/a10-rss-ai-digest.json`](workflows/a10-rss-ai-digest.json) | Lee tus feeds RSS/Atom y manda un digest de noticias elegido por IA. | Schedule (08:00) | RSS · Gemini · Telegram |
| [`workflows/a17-expense-logger.json`](workflows/a17-expense-logger.json) | Escribe `12 comida` y apunta una fila; escribe `/mes` para el total mensual por categoría. | Mensaje de Telegram | Telegram · Google Sheets |
| [`workflows/a18-read-it-later.json`](workflows/a18-read-it-later.json) | Mándale un enlace y descarga la página, la resume, la guarda y te responde con el resumen. | Mensaje de Telegram | Telegram · HTTP · Gemini · Google Sheets |

---

## Cómo encajan

```
Programados (te empujan a ti)            Bajo demanda (tú escribes al bot)
─────────────────────────────           ─────────────────────────────────
A15  buzón  ─┐                           A17  "12 comida" ─▶ fila + ✓
A16  agenda ─┼─▶ Telegram cada mañana    A17  "/mes"      ─▶ total del mes
A10  noticias┘                           A18  <enlace>    ─▶ resumen + fila
```

Los tres digests **programados** (A15, A16, A10) te llegan por temporizador — pueden compartir un
mismo bot. Los dos **interactivos** (A17, A18) escuchan tus mensajes.

> ⚠️ **Un solo trigger de Telegram activo por bot.** Telegram solo entrega los updates a un único
> webhook activo por token de bot. A17 y A18 usan un *trigger* de Telegram, así que no pueden estar
> activos a la vez en el **mismo** bot. Opciones: un bot para cada uno, o fusionarlos en un workflow
> que enrute por contenido (enlace → A18, si no → A17). Los digests programados no usan trigger de
> Telegram, así que nunca chocan.

---

## Puesta en marcha

### 1. Credenciales necesarias (solo para los workflows que uses)

| Credencial (tipo n8n) | La usan | Notas |
|---|---|---|
| **Telegram** (`telegramApi`) | todos | Token del bot vía [@BotFather](https://t.me/BotFather). |
| **Google Gemini** (`googlePalmApi`) | A15, A10, A18 | API key gratis en [Google AI Studio](https://aistudio.google.com/). Modelo `models/gemini-2.5-flash`. |
| **Gmail** (`gmailOAuth2`) | A15 | O cámbialo por un nodo IMAP (ver abajo). |
| **Google Calendar** (`googleCalendarOAuth2Api`) | A16 | |
| **Google Sheets** (`googleSheetsOAuth2Api`) | A17, A18 | |

### 2. Importar y mapear

n8n → **Workflows → Import from File** → elige un `*.json`. Mapea la credencial de cada nodo y
sustituye los placeholders de abajo.

### 3. Sustituir placeholders

| Placeholder | Dónde | Pon |
|---|---|---|
| `YOUR_CHAT_ID` | nodos Telegram / código guard | Tu chat id numérico ([@userinfobot](https://t.me/userinfobot)). |
| `YOUR_CALENDAR_ID` | A16 — *Today's events* | `primary` o el id de tu calendario. |
| `YOUR_SHEET_ID` | A17, A18 — nodos Sheets | El id de la URL de tu hoja. |
| `REPLACE_ME` (ids de credencial) | cada nodo con credencial | Se resuelve solo al mapear credenciales. |
| URLs de feed de ejemplo | A10 — *Feed list* | Tus propios feeds RSS/Atom. |

### 4. Activar

Activa el workflow. Los programados ya están. Para A17/A18, escribe al bot para probar.

---

## Notas por workflow

**A15 — Resumen de email.** Usa el nodo Gmail con la query `newer_than:1d -category:promotions
-category:social`. ¿Prefieres IMAP (IONOS, Zoho, tu servidor)? Sustituye el nodo Gmail por **Email
Read (IMAP)** y ajusta el código *Compile* para leer `from` / `subject` / `text`.

**A16 — Calendario.** La franja laboral para detectar huecos está en el código *Format*
(`WORK_START`/`WORK_END`, por defecto 09:00–19:00). No necesita IA.

**A10 — Digest RSS.** Pon tus feeds en el nodo *Feed list*. Se descartan los items de más de 24h; el
modelo elige los 5–8 más relevantes. Un feed que falle se omite (`continueRegularOutput`).

**A17 — Gastos.** Parsea mensajes como `12 comida`, `12€ comida`, `comida 12,50`. La primera palabra
de la descripción es la categoría. `/mes` lee la hoja y responde con el total del mes por categoría.
Crea una hoja/pestaña llamada `Expenses` con columnas `Date, Amount, Currency, Category, Note`.

**A18 — Guardar-para-leer.** Descarga la página por HTTP, la recorta a ~6000 caracteres de texto y
pide a Gemini un resumen + puntos clave + etiquetas. Se guarda en una pestaña `Reading list`
(`Date, Title, URL, Summary`). Las páginas que se renderizan con JavaScript pueden devolver poco
texto — es una limitación conocida de descargar solo el HTML.

---

## Seguridad

- **Saneado** — sin tokens, chat ids, ids de hoja, hosts ni feeds reales; solo placeholders.
- Los workflows interactivos (A17, A18) **restringen a un único chat id** para que solo tú los uses.
- Los secretos viven solo en las credenciales de n8n, nunca en el JSON del workflow.

## Licencia

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
