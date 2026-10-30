# Toolkit para clientes / agencia

Un servicio pequeño en Python para freelancers y agencias pequeñas que llevan webs de clientes. Vive
en tu servidor, lo arranca systemd y solo necesita Python 3.9 o superior (solo librería estándar,
sin `pip`):

- **Monitor de uptime de clientes**: comprueba las webs de tus clientes cada 5 minutos y te avisa por
  Telegram cuando una se cae, empieza a devolver errores o vuelve a funcionar.
- **Informe semanal de analítica**: cada lunes, visitantes, páginas vistas, páginas más vistas y
  fuentes de tráfico de [Plausible](https://plausible.io/) (o [Umami](https://umami.is/)) en un
  correo HTML para el cliente.
- **Generador de facturas**: un comando que convierte los datos de una factura (JSON) en un PDF con
  [Gotenberg](https://gotenberg.dev/) en tu propio servidor y se lo envía al cliente por correo.

Sin SaaS de pago: los PDF se generan en tu servidor y los datos salen de tu analítica.

> 🇬🇧 [English version](README.md)

---

## Cómo funciona

| Función | Cuándo se ejecuta | Qué necesita |
|---|---|---|
| Monitor de uptime | Dentro del servicio, cada `UPTIME_INTERVAL_MINUTES` (5) | Bot de Telegram |
| Informe semanal | Dentro del servicio, el `REPORT_DAY` a las `REPORT_TIME` (lunes, 09:00) | API key de Plausible o Umami, SMTP |
| Facturas | Cuando tú quieras: `python3 /opt/agency-toolkit/app/invoice.py factura.json` | Gotenberg, SMTP |

- **Un solo servicio**, `agency-toolkit`, que systemd ejecuta con su propio usuario de sistema. Lee
  `/etc/agency-toolkit/agency-toolkit.env` y programa las comprobaciones y el informe.
- **Cada función se apaga sola** mientras sus ajustes estén vacíos. Al arrancar, el servicio anota en
  el log cuáles están activas y, para las demás, qué ajustes faltan (`journalctl -u agency-toolkit`).
- **Uptime**: sin respuesta (timeout, DNS, error de TLS) o HTTP ≥ 500 es *caída*, HTTP ≥ 400 es
  *aviso* y lo demás está *bien* (sigue las redirecciones). Recibes **un aviso por cambio**: cuando
  una web se cae, pasa a aviso o se recupera, nunca en cada comprobación. El último estado de cada web
  se guarda en `/var/lib/agency-toolkit/state.json`, así que un reinicio no repite el aviso.
- **Informe**: cubre los últimos `REPORT_DAYS` (7) días completos hasta ayer, así que un lunes va del
  lunes al domingo anteriores. Usa la Stats API de Plausible (una llamada *aggregate* y dos
  *breakdown*) y envía un correo HTML con su versión en texto plano.
- **Facturas**: los totales se calculan con decimales exactos (cada línea redondeada a céntimos y el
  IVA sobre la base, redondeando la mitad hacia arriba). La plantilla HTML es
  `app/invoice_template.html`; cámbiale el estilo a tu gusto.
- Si una tarea programada empieza a fallar (Plausible caído, el SMTP rechaza el login...) te llega un
  mensaje por Telegram, y otro cuando vuelve a funcionar. Una vez por cambio, no en cada pasada.

## Puesta en marcha

Necesitas un servidor Linux con systemd y Python 3.9 o superior (AlmaLinux 9, Debian 11 o posterior y
Ubuntu 22.04 ya lo traen). Configura solo las partes que vayas a usar.

### 1. Instalar

Copia esta carpeta al servidor (por ejemplo, clonando el repositorio) y ejecuta, como root:

```bash
cd templates/client-agency-toolkit
sudo bash install.sh
```

Crea el usuario de sistema `agency-toolkit`, copia el código a `/opt/agency-toolkit`, crea
`/etc/agency-toolkit/agency-toolkit.env` a partir de
[`agency-toolkit.env.example`](agency-toolkit.env.example) (solo si todavía no existe) e instala la
unidad de systemd. No arranca nada. Para actualizar, vuelve a ejecutarlo después de bajar los
cambios: el código se sustituye y tu configuración se queda como está.

### 2. Bot de Telegram (avisos de uptime)

1. Habla con [@BotFather](https://t.me/BotFather), envía `/newbot` y copia el token en
   `TELEGRAM_BOT_TOKEN`.
2. Abre un chat con tu bot nuevo y pulsa **Iniciar**; si no, no puede escribirte.
3. Pide tu ID numérico a [@userinfobot](https://t.me/userinfobot) y ponlo en `TELEGRAM_CHAT_ID`. Para
   un grupo, añade el bot al grupo y usa el ID del grupo (empieza por `-`).

### 3. Webs que vigilar

```ini
UPTIME_SITES=Cliente A|https://example.com, Cliente B|https://shop.example.org, Cliente C|https://example.net/health
```

Cada elemento es `Nombre|URL`, separados por comas. El nombre es lo que verás en el aviso.

### 4. API key de Plausible (informe semanal)

En Plausible, entra en los ajustes de tu cuenta > **API keys** > **New API key**, elige la Stats API
y cópiala en `PLAUSIBLE_API_KEY`. `PLAUSIBLE_SITE_ID` es el dominio de la web tal y como aparece en
Plausible (`example.com`). Si tienes Plausible autoalojado, pon también tu instancia en
`PLAUSIBLE_URL`. En Plausible Cloud, comprueba que tu plan incluye la Stats API.

Pon el correo del cliente en `REPORT_TO` (puedes poner varios, separados por comas).

**¿Usas Umami?** Pon `ANALYTICS_PROVIDER=umami`, `UMAMI_API_URL` (`https://api.umami.is/v1` en Umami
Cloud, `https://umami.example.com/api` si es autoalojado), `UMAMI_WEBSITE_ID` (Settings > Websites >
Edit) y, o bien `UMAMI_API_KEY`, o bien, en un Umami autoalojado sin API keys, `UMAMI_USERNAME` y
`UMAMI_PASSWORD` (de una cuenta sin doble factor). El rebote y la duración media se calculan a partir
de las visitas, los rebotes y el tiempo total que da Umami.

### 5. SMTP (informe y facturas)

Vale cualquier buzón desde el que puedas enviar. Rellena `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` y
`SMTP_FROM` (`Tu Empresa <facturacion@example.com>`). `SMTP_SECURITY` puede ser `starttls` (puerto
587, el valor por defecto), `ssl` (puerto 465) o `none` (un relay local en el puerto 25, sin login si
`SMTP_USER` está vacío).

### 6. Gotenberg (facturas)

Gotenberg convierte el HTML de la factura en PDF. Con Docker es una línea, y solo se puede llegar a él
desde el propio servidor:

```bash
docker run -d --name gotenberg --restart unless-stopped -p 127.0.0.1:3000:3000 gotenberg/gotenberg:8
```

Después pon `GOTENBERG_URL=http://127.0.0.1:3000`.

### 7. Arrancar

```bash
sudo systemctl enable --now agency-toolkit
journalctl -u agency-toolkit -f
```

Las primeras líneas dicen qué funciones están activas. Cada vez que cambies la configuración:
`sudo systemctl restart agency-toolkit`.

## Facturas

Copia el ejemplo, rellénalo, pruébalo y envíalo:

```bash
cp /opt/agency-toolkit/invoice.example.json ~/factura-2026-001.json
nano ~/factura-2026-001.json
sudo python3 /opt/agency-toolkit/app/invoice.py ~/factura-2026-001.json --dry-run
sudo python3 /opt/agency-toolkit/app/invoice.py ~/factura-2026-001.json
```

Con `--dry-run` escribe `factura-2026-001.html` y `factura-2026-001.pdf` junto al JSON y no envía
nada (sin `GOTENBERG_URL` solo escribe el HTML). Sin él, el PDF se envía a `client_email` desde
`SMTP_FROM`. El `sudo` hace falta porque el comando lee el fichero de configuración, que solo pueden
leer root y el servicio; con `--config RUTA` puedes indicarle otro.

| Campo | Obligatorio | Notas |
|---|---|---|
| `invoice_number` | sí | Sale en la factura, en el asunto y en el nombre del PDF. |
| `seller_name`, `seller_taxid`, `seller_address` | el nombre | Tus datos (razón social, NIF, dirección). |
| `client_name`, `client_taxid`, `client_email` | nombre y email | `client_email` es a donde se envía. |
| `items` | sí | Líneas con `desc`, `qty` y `price` (números o textos como `"49.95"`). |
| `tax_rate` | no | Porcentaje de IVA, por ejemplo `21`. Por defecto `0`. |
| `currency` | no | Código ISO; por defecto `EUR`. |
| `date` | no | `AAAA-MM-DD`; si falta, la fecha de hoy. |
| `language` | no | `en` o `es` para esta factura; por defecto, `LANGUAGE`. |

Todos los valores se escapan antes de meterlos en la plantilla HTML.

## Ajustes

Todos están en `/etc/agency-toolkit/agency-toolkit.env`, uno por línea como `CLAVE=valor`, sin
comillas. Vacío significa "sin configurar".

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| `LANGUAGE` | `en` | `en` o `es`: avisos, informe y facturas. |
| `TIMEZONE` | la del servidor | Zona horaria del horario y las fechas del informe, como `Europe/Madrid`. |
| `TELEGRAM_BOT_TOKEN` | | Token del bot, de @BotFather. |
| `TELEGRAM_CHAT_ID` | | Chat que recibe los avisos. |
| `UPTIME_SITES` | | Elementos `Nombre\|URL` separados por comas. Vacío: monitor apagado. |
| `UPTIME_INTERVAL_MINUTES` | `5` | Minutos entre comprobaciones. |
| `UPTIME_TIMEOUT_SECONDS` | `10` | Segundos de espera antes de dar una web por caída. |
| `REPORT_TO` | | Destinatarios del informe, separados por comas. Vacío: informe apagado. |
| `REPORT_SITE_NAME` | el site ID | Nombre en el asunto y el título. |
| `REPORT_DAY` | `monday` | Día de envío (en inglés: `monday` ... `sunday`). |
| `REPORT_TIME` | `09:00` | Hora local de envío. |
| `REPORT_DAYS` | `7` | Días completos que cubre, hasta ayer. |
| `ANALYTICS_PROVIDER` | `plausible` | `plausible` o `umami`. |
| `PLAUSIBLE_URL` | `https://plausible.io` | Tu instancia, si es autoalojado. |
| `PLAUSIBLE_SITE_ID` | | Dominio de la web en Plausible. |
| `PLAUSIBLE_API_KEY` | | API key de la Stats API. |
| `UMAMI_API_URL` | | Raíz de la API: `https://api.umami.is/v1` o `https://umami.example.com/api`. |
| `UMAMI_WEBSITE_ID` | | ID de la web (UUID). |
| `UMAMI_API_KEY` | | API key... |
| `UMAMI_USERNAME`, `UMAMI_PASSWORD` | | ...o un usuario, en Umami autoalojado sin API keys. |
| `GOTENBERG_URL` | | URL base de Gotenberg. Vacío: facturas apagadas. |
| `SMTP_HOST` | | Servidor SMTP. Vacío: informe y facturas apagados. |
| `SMTP_SECURITY` | `starttls` | `starttls`, `ssl` o `none`. |
| `SMTP_PORT` | 587 / 465 / 25 | Según `SMTP_SECURITY`. |
| `SMTP_USER`, `SMTP_PASSWORD` | | Login SMTP; sin usuario no hace login. |
| `SMTP_FROM` | | Remitente, como `Tu Empresa <facturacion@example.com>`. |

## Cómo probarlo

**Tests unitarios** (sin red ni cuentas; Telegram, HTTP, SMTP y Gotenberg falsos):

```bash
cd templates/client-agency-toolkit
python3 -m unittest discover -s tests -t .
```

**En el servidor**, una vez configurado:

- **Uptime**: añade `Prueba|https://example.invalid` a `UPTIME_SITES` y reinicia. En menos de 5
  minutos te llega un aviso de "no responde", y nada más en las siguientes comprobaciones. Quítalo
  después.
- **Informe**: `sudo python3 /opt/agency-toolkit/app/report.py --dry-run > /tmp/informe.html` saca
  los datos reales y escribe el HTML del correo sin enviarlo. Sin `--dry-run`, envía el informe en ese
  momento.
- **Facturas**: el `--dry-run` de arriba; luego abre el PDF.

**Sin instalarlo** (en tu portátil, por ejemplo): copia `agency-toolkit.env.example` a `mi.env`,
rellénalo y ejecuta `mkdir -p /tmp/agency-toolkit && STATE_DIRECTORY=/tmp/agency-toolkit python3
app/toolkit.py mi.env`. `report.py` e `invoice.py` aceptan `--config mi.env`.

## Notas

- **Webs detrás de Cloudflare o de un WAF**: pueden contestar al monitor con un 403 (aviso). El
  monitor se identifica con el User-Agent `Mozilla/5.0 (compatible; agency-toolkit uptime monitor)`;
  déjalo pasar, o vigila una URL de salud que no tenga desafío.
- El informe usa la **Stats API v1 de Plausible** (`/api/v1/stats/aggregate` y `/breakdown`), las
  mismas llamadas que la versión de n8n.
- En Umami, las páginas se piden con el tipo de métrica `path` (Umami 3) y, si el servidor no lo
  acepta, con `url` (versiones anteriores).

## Cambios respecto a la versión de n8n

Sustituye a los tres workflows de n8n (A12, A13 y A14), que siguen en la etiqueta de git `n8n-final`.

- **Uptime (A12)**: un aviso por cambio de estado y otro cuando la web se recupera (A12 repetía el
  aviso cada 5 minutos mientras una web estaba caída y nunca decía cuándo volvía). La lista de webs
  pasa al fichero de configuración. Desaparecen el `expectStatus` por web de A12 y su `SLOW_MS`
  (estaba definido, pero no se usaba).
- **Informe (A14)**: se envía a las 09:00 en vez de a las 08:00. El periodo son los 7 últimos días
  completos con fechas explícitas (rango `custom` de Plausible) en vez del `7d` de Plausible, así que
  el correo muestra las fechas. Umami viene de serie en vez de tener que editar los nodos. El correo
  lleva versión en texto plano, y las cuatro tarjetas de cifras son una tabla para que más clientes
  de correo las muestren en fila.
- **Facturas (A13)**: un comando que lee un fichero JSON en vez de un disparador manual con un nodo
  Set. El PDF sale en A4 y con fondos (Gotenberg, por defecto, usa tamaño carta de EE. UU. y no
  imprime fondos, lo que dejaría el texto blanco de la cabecera de la tabla sobre blanco). Los textos
  siguen `LANGUAGE` y los importes usan decimales exactos.

## Estado

Portado desde la versión de n8n el 2026-10-30. Cubierto por tests unitarios; todavía no se ha
probado contra cuentas reales de Plausible, Umami, Gotenberg ni SMTP.

## Seguridad

- Los secretos viven solo en `/etc/agency-toolkit/agency-toolkit.env` (modo `640`,
  `root:agency-toolkit`). Nada de esta carpeta es real: solo placeholders.
- El servicio no abre ningún puerto: solo hace peticiones salientes. Deja Gotenberg escuchando en
  `127.0.0.1`.
- La unidad de systemd lo ejecuta con un usuario sin privilegios y una vista de solo lectura del
  sistema (solo puede escribir en `/var/lib/agency-toolkit`).

## Licencia

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
