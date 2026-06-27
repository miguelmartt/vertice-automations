# vertice-automations

Plantillas reutilizables de **n8n** — listas para importar, documentadas y seguras para autoalojar.
Mantenido por [Vérticedev](https://verticedev.es). Licencia [MIT](LICENSE).

> 🇬🇧 Prefer English? Read the [English README](README.md).

---

## Qué contiene

Cada automatización vive en su propia carpeta autocontenida dentro de [`templates/`](templates/), con
su(s) JSON de workflow, los scripts auxiliares y su propio README. Coge solo lo que necesites.

| Plantilla | Qué hace | Stack |
|---|---|---|
| [`vertiguard-vps-monitoring`](templates/vertiguard-vps-monitoring/) | **VertiGuard** — suite de 8 workflows para monitorizar un VPS autoalojado (servicios, disco/RAM, SSL, backups, fail2ban, actualizaciones, uptime externo y `/status` bajo demanda) con avisos por Telegram. | n8n · SSH · Telegram |

_Se irán añadiendo más plantillas (asistente IA por Telegram, digests RSS, registro de gastos, guardar-para-leer…)._

---

## Cómo usar una plantilla

1. Abre la carpeta de la plantilla y lee su README.
2. En n8n: **Workflows → Import from File** y elige el `*.json` que quieras.
3. Asigna las credenciales que pida el workflow (p. ej. una clave SSH, un bot de Telegram).
4. Sustituye los placeholders (ver el README de cada plantilla) y actívalo.

Todos los workflows vienen **inactivos** (`"active": false`): nada se ejecuta hasta que tú lo revisas.

---

## Placeholders y seguridad

Estas plantillas están **saneadas**. No contienen hosts, IPs, tokens, chat IDs ni claves reales,
solo placeholders que tú rellenas:

| Placeholder | Sustitúyelo por |
|---|---|
| `YOUR_CHAT_ID` | Tu chat ID de Telegram |
| `REPLACE_ME` (id de credencial) | Se resuelve solo al asignar credenciales en n8n |
| `example.com`, `n8n.example.com` | Tus dominios (variables del script) |
| `b2:my-backups` | Tu propio remoto/ruta de rclone |

Los secretos nunca van al repo: `.gitignore` bloquea claves, `.env` y ficheros de credenciales por defecto.
La seguridad **no** depende de que estos workflows sean privados — tu protección real son las claves SSH,
fail2ban y tu firewall, nada de eso se publica aquí.

---

## Contribuir

Se aceptan PRs — ver [CONTRIBUTING.md](CONTRIBUTING.md). Mantén las contribuciones saneadas (sin secretos
reales) y los workflows inactivos.

## Licencia

[MIT](LICENSE) © Vérticedev
