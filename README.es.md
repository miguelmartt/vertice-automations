# vertice-automations

Automatizaciones que viven en tu propio servidor: **servicios pequeños de Python gestionados por
systemd**, sin plataforma de automatización de por medio, sin nada que instalar con `pip` y sin
cuotas mensuales. Mantenido por [Vérticedev](https://verticedev.es). Licencia [MIT](LICENSE).

> 🇬🇧 Prefer English? Read the [English README](README.md).

---

## Qué contiene

Cada automatización vive en su propia carpeta autocontenida dentro de [`templates/`](templates/),
con su código, tests, instalador, unidad de systemd, configuración de ejemplo y README. Coge solo lo
que necesites.

| Plantilla | Qué hace | Habla con |
|---|---|---|
| [`vertiguard`](templates/vertiguard/) | **VertiGuard**: vigila un VPS con un solo bot de Telegram: avisa solo cuando algo cambia, manda un parte diario (servicios, recursos, seguridad, copias, SSL, Docker, actualizaciones) y tiene comandos y un panel de botones para consultarlo y actuar desde el móvil, con Gemini para preguntas en tus palabras. Incluye webhook para UptimeRobot. | Telegram · Gemini · UptimeRobot |
| [`form-email-to-telegram`](templates/form-email-to-telegram/) | Mensaje en Telegram en cuanto alguien envía el formulario de contacto de tu web: vigila el buzón por IMAP, sin tocar la web. | IMAP · Telegram |
| [`telegram-personal-assistant`](templates/telegram-personal-assistant/) | Un asistente personal en Telegram: resumen del correo por la mañana, agenda del día, noticias de tus RSS elegidas por IA, registro de gastos y un guardar-para-leer que resume cualquier enlace. | Gmail · Calendar · Sheets · Gemini · Telegram |
| [`client-agency-toolkit`](templates/client-agency-toolkit/) | Para freelancers y agencias: monitor de uptime de las webs de tus clientes, generador de facturas (JSON → HTML → PDF → email) e informe semanal de analítica por correo. | Plausible · Gotenberg · SMTP · Telegram |

---

## Por qué servicios de Python y no una plataforma

Empezaron siendo flujos de n8n. Como código resultan más fáciles de mantener:

- **Ligeros.** Una plantilla gasta unas decenas de MB de RAM; no hay plataforma, base de datos ni
  editor que mantener encendidos y actualizados.
- **Revisables.** Cada cambio es un diff en git, con tests. Nada escondido en un JSON exportado.
- **Más seguros.** No hay un panel web que guarde todas tus credenciales. Cada servicio corre con su
  propio usuario de sistema, habla con Telegram por long polling (sin abrir puertos) y guarda sus
  secretos en un único fichero de root.
- **Portables.** Python 3.9+ y solo la librería estándar: funcionan en un AlmaLinux 9, Debian o
  Ubuntu recién instalado.

Las versiones de n8n siguen en la etiqueta [`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final)
por si aún las quieres.

---

## Cómo usar una plantilla

```bash
git clone https://github.com/miguelmartt/vertice-automations.git
cd vertice-automations
sudo bash templates/<plantilla>/install.sh
```

Después rellena `/etc/<servicio>/<servicio>.env` como explica el README de la plantilla y arráncala
con `systemctl enable --now <servicio>`. Volver a ejecutar el instalador tras un `git pull` actualiza
el código y conserva tu configuración. Logs: `journalctl -u <servicio> -f`.

---

## Seguridad

Las plantillas están **saneadas**: sin hosts, IPs, tokens, chat IDs ni claves reales, solo
placeholders (`YOUR_CHAT_ID`, `REPLACE_ME`, `example.com`). Tus secretos van en
`/etc/<servicio>/<servicio>.env` (modo `640`, solo lo lee el usuario del servicio) y nunca en el
repo; `.gitignore` bloquea los `.env` y las claves. Donde hace falta root (las sondas de VertiGuard),
se pasa por una única regla de `sudo` para un conjunto fijo de scripts.

---

## Contribuir

Los PR son bienvenidos: en [CONTRIBUTING.md](CONTRIBUTING.md) están la estructura y las convenciones
que sigue cada plantilla.

## Licencia

[MIT](LICENSE) © Vérticedev
