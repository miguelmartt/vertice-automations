# Asistente personal por Telegram

Un servicio pequeño en Python que convierte un bot de Telegram en tu asistente personal: **resumen
del correo** por la mañana, **agenda del día** con tus huecos libres, **resumen de noticias** de tus
feeds RSS hecho con IA, **registro de gastos** y **guardar para leer**, que resume cualquier enlace que
le mandes. La IA es **Google Gemini** (capa gratuita); los gastos y los enlaces guardados van a
**Google Sheets**.

Solo librería estándar de Python 3.9+, lo arranca systemd y no abre puertos (el bot usa long polling).

> 🇬🇧 [English version](README.md)

**Estado:** portado de la versión de n8n el 2026-10-30. Cubierto por tests unitarios; todavía no se ha
probado contra cuentas reales de Google. Los workflows de n8n siguen en la etiqueta
[`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final).

---

## Qué hace

| Función | Cuándo | Necesita | Qué recibes |
|---|---|---|---|
| Agenda del día | cada día, 07:30 | Google | Los eventos de hoy y tus huecos libres (de 30 min o más) en horario laboral. |
| Resumen del correo | cada día, 08:00 | Google + Gemini | El correo de las últimas 24 h agrupado en *requiere respuesta / para tu información / probablemente ruido*. |
| Resumen de noticias | cada día, 08:00 | Gemini + feeds | Los 5–8 titulares más relevantes de las últimas 24 h de tus feeds RSS/Atom. |
| Registro de gastos | escribes `12 comida` | Google + hoja de cálculo | Una fila en la pestaña `Expenses`; `/mes` (o `/month`) te da el total del mes por categoría. |
| Guardar para leer | mandas un enlace | Google + hoja de cálculo + Gemini | La página resumida (resumen, 3 ideas clave y 3 etiquetas), guardada en la pestaña `Reading list`. |

Cada función se activa sola cuando sus ajustes están rellenos, así que puedes empezar solo con las
que quieras. Al arrancar, el journal dice qué funciones están activas y qué le falta a cada una de las
demás.

## Cómo funciona

Un proceso con dos hilos:

```
hilo del programador                      hilo principal: long polling de Telegram
────────────────────                      ────────────────────────────────────────
07:30 agenda    (Calendar)        ─┐      tu mensaje ─▶ solo se atiende a TELEGRAM_CHAT_ID
08:00 correo    (Gmail + Gemini)  ─┼─▶ Telegram      /mes, /month   ─▶ gastos del mes
08:00 noticias  (RSS + Gemini)    ─┘                 otro /comando  ─▶ ayuda
                                                     lleva enlace   ─▶ guardar para leer
                                                     lo demás       ─▶ gasto (12 comida)
```

- **Enrutado.** En la versión de n8n, gastos y guardar para leer eran dos disparadores de Telegram
  distintos que no podían compartir bot. Aquí un solo bot reparte cada mensaje: primero los comandos,
  después los enlaces (el primer `http(s)://` del texto o del pie de foto, o un enlace escondido
  detrás de texto con formato) y todo lo demás se lee como un gasto. Por tanto,
  `12 https://example.com` es un enlace, no un gasto. Si un mensaje no lleva importe, el bot te
  explica cómo escribirlo.
- **Gastos.** `12 comida`, `12€ comida`, `comida 12,50`, `$12 taxi`, `15 usd taxi`: el primer número
  es el importe; `€`, `eur`, `euros`, `$` o `usd` delante o detrás marcan la moneda (si no,
  `EXPENSE_CURRENCY`); el resto del texto es la nota y su primera palabra, en minúsculas, la
  categoría. La fecha es la de hoy en tu zona horaria.
- **Resúmenes.** El correo se lee con la búsqueda de Gmail `EMAIL_QUERY` (por defecto, el último día
  sin promociones ni redes sociales). De los feeds se descartan las entradas de más de 24 h (si no
  hay ninguna tan reciente, se usan las últimas) y un feed que falle se salta. Si no hay correo o no
  hay noticias, te llega un mensaje corto de «nada nuevo» y no se llama a Gemini.
- **Fallos.** Si un resumen falla (Google caído, un token revocado, ningún feed accesible...) te llega
  un mensaje por Telegram, y otro cuando vuelve a funcionar; nunca uno por cada intento. Si un
  mensaje tuyo no se puede procesar, el bot te responde con el error.
- **Reinicios.** El offset de Telegram se guarda en `/var/lib/personal-assistant/state.json`, así que
  un reinicio nunca procesa dos veces el mismo mensaje (ni apunta dos veces el mismo gasto).
- **Las páginas** se descargan por HTTP normal (hasta 2 MB), se quitan scripts y estilos y los
  primeros 6.000 caracteres de texto van a Gemini. Las páginas que necesitan JavaScript pueden dar
  poco texto o ninguno; el enlace se guarda igualmente, con el resumen vacío.

## Puesta en marcha

Necesitas un servidor Linux con systemd y Python 3.9 o superior (AlmaLinux 9 o Debian 11 y
posteriores, tal cual vienen, valen) con salida a HTTPS. Para Google, además, un ordenador con
navegador y Python para autorizar el acceso una sola vez.

### 1. Instalar

```bash
git clone https://github.com/miguelmartt/vertice-automations.git
cd vertice-automations/templates/telegram-personal-assistant
sudo bash install.sh
```

Crea el usuario de sistema `personal-assistant`, copia el código a `/opt/personal-assistant`, la
configuración a `/etc/personal-assistant/personal-assistant.env` (modo 640; si ya existe, no la
toca) y la unidad de systemd. La primera vez no arranca el servicio.

### 2. Bot de Telegram y chat ID

1. Habla con [@BotFather](https://t.me/BotFather), envía `/newbot` y copia el token en
   `TELEGRAM_BOT_TOKEN`. Usa un bot solo para este asistente: los mensajes de un bot solo los puede
   leer un programa a la vez. (Si el bot tenía un webhook, por ejemplo de n8n, el servicio lo quita al
   arrancar.)
2. Escribe cualquier cosa a tu bot nuevo, abre en el navegador
   `https://api.telegram.org/botTU_TOKEN/getUpdates` y copia el número de `"chat":{"id":...}` en
   `TELEGRAM_CHAT_ID`. ([@userinfobot](https://t.me/userinfobot) también te lo dice.)

### 3. Clave de Gemini (resumen del correo, de noticias y guardar para leer)

Crea una clave gratuita en [Google AI Studio](https://aistudio.google.com/) (*Get API key*) y ponla
en `GEMINI_API_KEY`.

### 4. Cuenta de Google (correo, agenda, gastos y guardar para leer)

El asistente habla con Gmail, Calendar y Sheets con un cliente OAuth tuyo:

1. En la [consola de Google Cloud](https://console.cloud.google.com/), crea un proyecto (por ejemplo,
   `personal-assistant`).
2. **APIs & Services → Library**: activa **Gmail API**, **Google Calendar API** y **Google Sheets
   API** (solo las que vayas a usar).
3. **Google Auth Platform** (la pantalla de consentimiento OAuth): pulsa *Get started*, ponle un
   nombre y tu correo, elige **External** como público (o *Internal* si usas Google Workspace) y
   termina.
4. **Audience → Publish app**, para que quede *In production*. Mientras está en *Testing*, Google
   caduca el refresh token a los 7 días. Como la app no está verificada, la página de consentimiento
   avisa de que «Google no ha verificado esta aplicación»: es tu propia app, así que pulsa
   *Configuración avanzada → Ir a ... (no seguro)*.
5. **Clients → Create client**, tipo **Desktop app**, y descarga su fichero JSON.
6. En tu ordenador (no en el servidor), desde esta carpeta:

   ```bash
   python3 app/google_auth.py ~/Downloads/client_secret_XXXX.json
   ```

   Se abre el navegador con la página de consentimiento de Google; elige la cuenta y permite el
   acceso. El script recoge la respuesta en `http://127.0.0.1:<puerto aleatorio>` e imprime tres
   líneas (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`) para pegar en la
   configuración. Sin el fichero JSON, te pide el ID y el secreto del cliente. Pide `gmail.readonly`,
   `calendar.readonly` y `spreadsheets`; para dar menos acceso, añade por ejemplo
   `--scopes calendar,sheets`. (El script está en inglés, como los logs.)

El refresh token da acceso a esos permisos de tu cuenta: guárdalo solo en el fichero de
configuración. Puedes revocarlo cuando quieras en
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).

### 5. Hoja de cálculo (gastos y guardar para leer)

Crea una hoja de Google en la cuenta que has autorizado, con dos pestañas y estas cabeceras en la
fila 1:

| Pestaña | A | B | C | D | E |
|---|---|---|---|---|---|
| `Expenses` | Date | Amount | Currency | Category | Note |
| `Reading list` | Date | Title | URL | Summary | |

Las columnas tienen que ir en ese orden (los nombres de las cabeceras dan igual). Pon el ID de su URL
(`docs.google.com/spreadsheets/d/TU_ID_DE_HOJA/edit`) en `SPREADSHEET_ID`. Los nombres de las
pestañas se cambian con `EXPENSES_SHEET` y `READING_SHEET`. Los valores se escriben tal cual (las
fechas como texto `AAAA-MM-DD`, los importes como números), nunca como fórmulas; `/mes` suma las filas
cuya fecha empieza por el `AAAA-MM` actual.

### 6. Arrancar

```bash
sudo nano /etc/personal-assistant/personal-assistant.env   # rellena lo que vayas a usar
sudo systemctl enable --now personal-assistant
journalctl -u personal-assistant -f
```

Las primeras líneas dicen qué está activo, por ejemplo:

```
INFO assistant: email digest: on, every day at 08:00
INFO assistant: calendar agenda: on, every day at 07:30
INFO assistant: news digest: off (not set: RSS_FEEDS)
INFO assistant: expense logger: on
INFO assistant: read-it-later: on
```

Después de cambiar la configuración: `sudo systemctl restart personal-assistant`.

## Ajustes

Todos en `/etc/personal-assistant/personal-assistant.env`, un `CLAVE=valor` por línea, sin comillas.
Un ajuste vacío que no tiene valor por defecto desactiva su función.

| Ajuste | Por defecto | Lo usa | Qué es |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | (obligatorio) | todo | Token del bot de @BotFather. |
| `TELEGRAM_CHAT_ID` | (obligatorio) | todo | El único chat al que responde el bot, y adonde van los resúmenes. |
| `LANGUAGE` | `en` | todo | `en` o `es`: mensajes y resúmenes de la IA. |
| `TIMEZONE` | hora del servidor | todo | Zona horaria de las horas de envío y de las fechas de la hoja, como `Europe/Madrid`. |
| `GEMINI_API_KEY` | vacío | correo, noticias, guardar para leer | Clave de Google AI Studio. |
| `GEMINI_MODEL` | `gemini-flash-latest` | correo, noticias, guardar para leer | Modelo de Gemini. |
| `GOOGLE_CLIENT_ID` | vacío | correo, agenda, gastos, guardar para leer | Cliente OAuth de tipo Desktop app. |
| `GOOGLE_CLIENT_SECRET` | vacío | correo, agenda, gastos, guardar para leer | Su secreto. |
| `GOOGLE_REFRESH_TOKEN` | vacío | correo, agenda, gastos, guardar para leer | El que imprime `app/google_auth.py`. |
| `EMAIL_DIGEST_TIME` | vacío (ejemplo: `08:00`) | correo | Hora de envío, `HH:MM`. |
| `EMAIL_QUERY` | `newer_than:1d -category:promotions -category:social` | correo | Búsqueda de Gmail de los mensajes a resumir. |
| `EMAIL_MAX_MESSAGES` | `25` | correo | Máximo de mensajes que lee. |
| `CALENDAR_DIGEST_TIME` | vacío (ejemplo: `07:30`) | agenda | Hora de envío, `HH:MM`. |
| `CALENDAR_ID` | `primary` | agenda | Calendario que lee (`primary` o el ID de los ajustes del calendario). |
| `CALENDAR_WORK_START` | `09:00` | agenda | Inicio del horario laboral para los huecos libres. |
| `CALENDAR_WORK_END` | `19:00` | agenda | Fin del horario laboral. |
| `NEWS_DIGEST_TIME` | vacío (ejemplo: `08:00`) | noticias | Hora de envío, `HH:MM`. |
| `RSS_FEEDS` | vacío | noticias | URLs de los feeds, separadas por comas. |
| `SPREADSHEET_ID` | vacío | gastos, guardar para leer | ID de la hoja de cálculo. |
| `EXPENSES_SHEET` | vacío (ejemplo: `Expenses`) | gastos | Pestaña de los gastos. |
| `EXPENSE_CURRENCY` | `€` | gastos | Moneda cuando el mensaje no dice ninguna. |
| `READING_SHEET` | vacío (ejemplo: `Reading list`) | guardar para leer | Pestaña de los enlaces guardados. |

Los valores «ejemplo» son los de `personal-assistant.env.example`: son las horas de los antiguos
workflows de n8n, así que si los dejas, los resúmenes siguen activos.

## Pruebas

Tests unitarios (sin red ni cuentas), desde esta carpeta:

```bash
python3 -m unittest discover -s tests -t .
```

Cubren el enrutado de mensajes, la lectura de gastos y los totales del mes, el parseo de RSS/Atom,
la construcción de los tres resúmenes, la renovación y la caché del token de Google, el texto de las
páginas de guardar para leer y qué funciones se activan con cada configuración.

En el servidor, con el servicio en marcha, manda al bot `/help`, `12 comida`, `/mes` y un enlace, y
mira la hoja. Para probar un resumen sin esperar a la mañana, pon su hora un par de minutos más tarde,
reinicia el servicio y sigue `journalctl -u personal-assistant -f`.

Para probarlo en tu ordenador, copia la configuración de ejemplo, rellénala y ejecuta
`STATE_DIRECTORY=. python3 app/assistant.py mi-prueba.env` (Ctrl+C lo para). Para antes el servicio
del servidor: los mensajes de un bot solo los puede leer un programa.

## Actualizar

```bash
git pull
sudo bash install.sh   # conserva tu configuración y reinicia el servicio si está en marcha
```

## Cambios respecto a la versión de n8n

- Un solo bot para los gastos y guardar para leer, con el enrutado de arriba (antes hacía falta un bot
  para cada uno). También vale `/month` además de `/mes`, y `/help` dice qué está activo.
- Mensajes en inglés o en español (`LANGUAGE`); los resúmenes de la IA salen en ese idioma.
- Arreglos en los gastos: `12 euros comida` ya no deja «os» en la nota, `$12` se lee como dólares, un
  gasto sin descripción va a la categoría «(sin categoría)» y la fecha es la local (n8n usaba la fecha
  UTC, así que los gastos de madrugada caían en el día anterior).
- Sin correo o sin noticias: un mensaje fijo en vez de una llamada a Gemini. Cada resumen empieza con
  una línea de título.
- Una página que no se puede leer se guarda con el resumen vacío en vez de con un «no se pudo leer»
  escrito por la IA; los valores van a Sheets tal cual, así que el título de una página nunca se puede
  ejecutar como fórmula.
- Si no se puede leer ningún feed, el resumen de noticias avisa del fallo en vez de decir «nada
  nuevo».

## Seguridad

- **Saneado:** en este repo no hay tokens, chat IDs, IDs de hojas ni feeds reales, solo placeholders.
- El bot atiende a un único chat ID e ignora todo lo demás.
- Los secretos viven solo en `/etc/personal-assistant/personal-assistant.env` (`640`,
  `root:personal-assistant`).
- Gmail y Calendar se usan con permisos de solo lectura; Sheets necesita escritura para añadir filas.
- El servicio corre con su propio usuario sin privilegios y una vista de solo lectura del sistema
  (endurecimiento de systemd en `systemd/personal-assistant.service`).

## Licencia

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
