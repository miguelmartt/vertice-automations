# Toolkit para clientes / agencia (n8n)

Tres workflows de **n8n** para freelancers y agencias pequeñas que gestionan cosas de clientes: un
**monitor de uptime** de las webs que llevas, un **generador de facturas** (datos → HTML → PDF →
email) y un **reporte de analytics semanal** que se envía al cliente por correo. Sin SaaS de pago:
los PDF se generan con [Gotenberg](https://gotenberg.dev/) (autoalojable) y las analíticas salen de
[Plausible](https://plausible.io/) / [Umami](https://umami.is/).

> 🇬🇧 [English version](README.md)

Cada workflow es independiente — importa solo los que quieras. Todos salen **inactivos**
(`"active": false`), así que nada se ejecuta hasta que lo revises.

---

## Qué incluye

| Fichero | Qué hace | Disparador | Stack |
|---|---|---|---|
| [`workflows/a12-client-uptime-monitor.json`](workflows/a12-client-uptime-monitor.json) | Comprueba una lista de webs de clientes cada 5 min y avisa por Telegram solo cuando una cae o devuelve error. | Schedule (5 min) | HTTP · Telegram |
| [`workflows/a13-invoice-pdf-generator.json`](workflows/a13-invoice-pdf-generator.json) | Convierte los datos de la factura en un HTML con estilo, lo pasa a PDF con Gotenberg y lo envía al cliente por email. | Manual / Webhook | Set · Gotenberg · SMTP |
| [`workflows/a14-weekly-analytics-report.json`](workflows/a14-weekly-analytics-report.json) | Cada lunes saca visitantes / páginas vistas / top páginas / top fuentes de Plausible y envía un informe HTML. | Schedule (semanal) | Plausible · SMTP |

---

## Puesta en marcha

### 1. Credenciales necesarias (solo para los workflows que uses)

| Credencial (tipo n8n) | La usa | Notas |
|---|---|---|
| **Telegram** (`telegramApi`) | A12 | Token de bot de [@BotFather](https://t.me/BotFather). |
| **SMTP** (`smtp`) | A13, A14 | Cualquier cuenta SMTP (tu proveedor de correo). |
| **Header Auth** (`httpHeaderAuth`) | A14 | Name = `Authorization`, Value = `Bearer YOUR_PLAUSIBLE_API_KEY`. |

A13 necesita además una instancia de **Gotenberg** accesible (sin credencial, es un servicio HTTP
interno). Lo más rápido: `docker run --rm -p 3000:3000 gotenberg/gotenberg:8`. Si n8n y Gotenberg
comparten red Docker, usa el nombre del servicio como host (p. ej. `http://gotenberg:3000`).

### 2. Importar y mapear

n8n → **Workflows → Import from File** → elige un `*.json`. Mapea la credencial de cada nodo y luego
sustituye los placeholders de abajo.

### 3. Sustituir los placeholders

| Placeholder | Dónde | Sustituir por |
|---|---|---|
| `YOUR_CHAT_ID` | A12 — nodo Telegram | Tu chat id numérico (de [@userinfobot](https://t.me/userinfobot)). |
| lista de sitios | A12 — code *Site list* | Las URLs y nombres reales de tus clientes. |
| `YOUR_GOTENBERG_HOST` | A13 — nodo *HTML → PDF* | Tu host de Gotenberg (p. ej. `gotenberg` o `localhost`). |
| campos emisor / cliente | A13 — *Invoice data* | Tus datos de empresa y las líneas de factura. |
| `example.com` `client@example.com` | A13, A14 — nodos Set | El site id y el destinatario reales. |
| `https://plausible.io` | A14 — *Config* | Déjalo para Plausible Cloud, o tu URL autoalojada. |
| `YOUR_PLAUSIBLE_API_KEY` | A14 — credencial Header Auth | Tu API key de Plausible (Settings → API keys). |

### 4. Activar

Activa A12 y A14 (programados). A13 va a demanda — ábrelo y dale **Execute**, o cambia el trigger
manual por un Webhook / un trigger de "fila nueva" para engancharlo a tu flujo de facturación.

---

## Notas por workflow

**A12 — Monitor de uptime.** Edita el array `SITES` del nodo *Site list*. Una petición se considera
**caída** con HTTP ≥ 500 o sin respuesta (timeout/DNS), y **aviso** con HTTP ≥ 400. Solo los fallos
llegan a Telegram, así que una pasada sana es silenciosa. Ajusta `SLOW_MS` / `TIMEOUT_MS` en el mismo
nodo. Para avisos de recuperación por sitio, combínalo con los patrones de `vertiguard-vps-monitoring`.

**A13 — Generador de facturas.** El nodo *Invoice data* guarda emisor, cliente, tipo de IVA y un
array `items` (`desc`, `qty`, `price`). Los totales y el IVA se calculan en *Render HTML*, así que la
plantilla es solo presentación — reestiliza el CSS a tu gusto. Gotenberg recibe el HTML como
`index.html` y devuelve el PDF, que se adjunta al correo. Sin API keys externas, nada sale de tu
infraestructura. ¿Prefieres un conversor en la nube? Apunta el nodo HTTP a PDFShift/APITemplate.

**A14 — Reporte semanal.** Usa tres llamadas a la Stats API de Plausible (aggregate + dos
breakdowns). Para **Plausible autoalojado** solo cambia la URL base. Para **Umami**, cambia los
endpoints/campos (`/api/websites/{id}/stats` y `/metrics`) en los nodos HTTP y ajusta *Format
report* — la estructura es la misma. El informe se envía como email HTML; pon el correo del cliente
en *Config*.

---

## Seguridad

- **Saneado** — sin tokens, chat ids, hosts, site ids ni API keys reales en el repo, solo
  placeholders.
- Los secretos viven solo en las credenciales de n8n, nunca en el JSON del workflow.
- El aviso de Telegram de A12 y los emails de A13/A14 van solo a donde tú configures.

## Licencia

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
