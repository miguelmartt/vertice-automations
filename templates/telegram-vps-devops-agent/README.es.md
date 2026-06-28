# Agente DevOps de VPS por Telegram (n8n + Gemini)

Maneja y consulta tu **VPS autoalojado** desde Telegram. Dos formas de usarlo:

- **Texto libre** — preguntas en lenguaje natural (*"¿cómo va el servidor?"*, *"¿ataques hoy?"*) y un
  agente IA (Gemini) obtiene un snapshot en vivo por SSH y responde.
- **`/menu`** — un menú de botones para tocar: consultar estado (servicios, disco, RAM, uptime, SSL,
  fail2ban, backups) y ejecutar **acciones de control** (reiniciar nginx / n8n / MariaDB, desbanear una
  IP) — cada acción de control tras un paso explícito de **Confirmar / Cancelar**.

> 🇬🇧 [English version](README.md)

Se apoya en los scripts de [`vertiguard-vps-monitoring`](../vertiguard-vps-monitoring/) y el mismo
usuario SSH dedicado de privilegios mínimos. Probado en AlmaLinux 9 con n8n en Docker y una API key
gratuita de Google Gemini.

---

## Cómo funciona

```
Telegram (mensaje o toque de boton)
   │
   ▼
Telegram Trigger ─▶ Guard (allowlist: solo tu chat) ─▶ Route
                                                        ├─ /menu  → enviar menu de botones (HTTP)
                                                        ├─ boton  → snapshot / control + respuesta
                                                        └─ texto  → AI Agent (Gemini + memoria + tool)
```

- Las **lecturas** ejecutan `snapshot.sh` por SSH y formatean el dato pedido.
- Las **acciones de control** muestran una confirmación; al *Confirmar* ejecutan un script pequeño y
  dedicado (`restart_*.sh`, `unban_ip.sh`) por SSH y reportan el resultado.
- El **texto libre** va a un agente Gemini con memoria de conversación y una herramienta `get_vps_status`.

Los teclados se envían con un nodo **HTTP Request** a la API de Telegram (más fiable que la UI de
teclados del nodo nativo entre versiones).

Incluye dos workflows:

| Fichero | Rol |
|---|---|
| [`workflows/telegram-vps-devops-agent.json`](workflows/telegram-vps-devops-agent.json) | Principal: trigger, router, menú, control + confirmación, path de texto IA |
| [`workflows/vps-snapshot-subworkflow.json`](workflows/vps-snapshot-subworkflow.json) | Destino del tool del agente: ejecuta `snapshot.sh` y devuelve el JSON |

---

## Scripts (instalar en el VPS, en `/opt/vertiguard/`)

| Script | Para qué |
|---|---|
| `snapshot.sh` | Snapshot combinado de solo lectura (servicios, disco, RAM, uptime, SSL, fail2ban, backups) |
| `restart_nginx.sh` | `systemctl restart nginx` + reporte |
| `restart_n8n.sh` | `docker restart` del contenedor n8n + reporte |
| `restart_mariadb.sh` | `systemctl restart mariadb` + reporte |
| `unban_ip.sh <ip>` | `fail2ban-client unban` (valida la IP) |

Todos devuelven JSON en una línea y corren como el usuario dedicado `vertiguard` vía la regla sudoers
acotada (`/opt/vertiguard/*.sh`) — sin privilegios extra más allá de ese comodín.

---

## Puesta en marcha

### 1. Instala los scripts en el VPS (como root)

Necesitas la base de VertiGuard (usuario `vertiguard` + sudoers acotado) — si usas
[`vertiguard-vps-monitoring`](../vertiguard-vps-monitoring/), ya la tienes.

```bash
sudo install -m 755 -o root -g root snapshot.sh restart_nginx.sh restart_n8n.sh \
  restart_mariadb.sh unban_ip.sh /opt/vertiguard/
sudo -u vertiguard sudo -n /opt/vertiguard/snapshot.sh   # prueba: imprime una linea JSON
```

Ajusta las variables del principio de `snapshot.sh` (dominios, contenedor, remoto de backup) y pon
`N8N_CONTAINER` en `restart_n8n.sh` si tu contenedor no se llama `n8n`.

### 2. Crea un bot de Telegram dedicado

[@BotFather](https://t.me/BotFather) → `/newbot` → copia el **token**. Usa un **bot nuevo** (Telegram
solo permite un Trigger activo por bot).

### 3. Saca una API key gratis de Google Gemini

[Google AI Studio](https://aistudio.google.com/app/apikey) → *Create API key*. En n8n crea una
credencial **Google Gemini (PaLM) API**. (Usa `gemini-2.5-flash` — el tier gratis de `gemini-2.0-flash`
puede ser 0.)

### 4. Importa y conecta los dos workflows

1. Importa primero `vps-snapshot-subworkflow.json`, luego `telegram-vps-devops-agent.json`.
2. **Credenciales:** Telegram Trigger → tu bot; los tres nodos SSH → tu clave SSH del VPS;
   Google Gemini Chat Model → tu key de Gemini.
3. **Token para enviar:** abre el nodo **TG send** y pon tu token en la URL —
   `https://api.telegram.org/bot<TU_TOKEN>/sendMessage`.
4. **Allowlist:** en el nodo **Guard**, pon `ALLOWED_CHAT_ID` con tu chat id numérico
   (de [@userinfobot](https://t.me/userinfobot)).
5. **Enlace del tool:** abre **get_vps_status** → Workflow → elige el sub-workflow del snapshot.
6. **Activa** el workflow principal.

> Si el bot deja de recibir tras publicar, haz **Unpublish → Publish** una vez para re-registrar el
> webhook de Telegram.

### 5. Úsalo

Manda `/menu` para los botones, o charla directamente: *"¿cómo va el servidor?"*. Los botones de
control piden confirmación antes de hacer nada.

---

## Referencia de configuración

| Placeholder | Dónde | Sustitúyelo por |
|---|---|---|
| `ALLOWED_CHAT_ID = 0` | nodo Guard | Tu chat id numérico de Telegram |
| `REPLACE_BOT_TOKEN` | URL del nodo TG send | El token de tu bot |
| `REPLACE_WITH_SUBWORKFLOW_ID` | get_vps_status | Se pone solo al elegir el sub-workflow |
| `REPLACE_ME` (ids de credencial) | varios | Se resuelven al asignar credenciales |
| `models/gemini-2.5-flash` | nodo Gemini | Cualquier modelo que tu key permita |

Esquema de callbacks (por si lo amplías): `r:*` lecturas, `c:nginx|c:n8n|c:mariadb` → confirmar,
`c:unban` → listar IPs baneadas, `ok:*` → ejecutar, `x` → cancelar.

---

## Seguridad

- **Allowlist por chat id** — el bot ignora a todos menos a ti. Controla tu servidor.
- **Paso de confirmación** — toda acción de control requiere un *Confirmar* explícito.
- **Privilegio mínimo** — corre como el usuario dedicado `vertiguard`, limitado a `/opt/vertiguard/*.sh`.
  Los scripts de control son pequeños y fijos (reiniciar un servicio, desbanear una IP validada) — nada destructivo.
- **Saneado** — sin hosts, tokens, claves ni chat ids reales en el repo.

## Licencia

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
