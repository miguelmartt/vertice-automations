# VertiGuard — suite de monitorización de VPS para n8n

Ocho workflows de **n8n** pequeños y enfocados que vigilan un VPS Linux autoalojado y te avisan por
**Telegram**. Cada uno ejecuta por SSH un script de shell minúsculo y endurecido, devuelve JSON en una
línea y solo te escribe cuando algo cambia de verdad — señal, no ruido.

> 🇬🇧 [English version](README.md)

Probado en **AlmaLinux 9 / familia RHEL** con **n8n en Docker**. Se adapta fácil a Debian/Ubuntu
(cambia `dnf` por `apt` en el script de actualizaciones).

---

## Los workflows

| # | Fichero | Disparador | Qué vigila | Avisa cuando |
|---|---|---|---|---|
| 01 | [`01-service-monitor.json`](workflows/01-service-monitor.json) | cada 5 min | nginx, MariaDB, n8n (Docker), 2 URLs | un servicio cae / se recupera |
| 02 | [`02-disk-ram.json`](workflows/02-disk-ram.json) | cada hora | uso de disco `/` y RAM | el uso supera el 80% (configurable) |
| 03 | [`03-ssl-expiry.json`](workflows/03-ssl-expiry.json) | diario 09:00 | certificados Let's Encrypt | a un certificado le quedan < 15 días |
| 04 | [`04-backup-watchdog.json`](workflows/04-backup-watchdog.json) | diario 06:00 | backup de hoy en un remoto rclone | falta la copia de hoy |
| 05 | [`05-fail2ban-report.json`](workflows/05-fail2ban-report.json) | diario 09:00 | jail `sshd` de fail2ban | resumen diario (IPs baneadas, intentos) |
| 06 | [`06-external-uptime.json`](workflows/06-external-uptime.json) | webhook | ping externo dead-man / uptime | el server deja de responder desde fuera |
| 07 | [`07-system-updates.json`](workflows/07-system-updates.json) | lunes 09:00 | actualizaciones `dnf` pendientes | recuento semanal de paquetes |
| 19 | [`19-status-on-demand.json`](workflows/19-status-on-demand.json) | Telegram `/status` | snapshot completo a demanda | le envías `/status` al bot |

> **Ojo:** Telegram solo admite **un Trigger activo por bot**. El workflow 19 usa un Telegram Trigger,
> así que si quieres más workflows con trigger de Telegram, usa un segundo bot para ellos.

---

## Arquitectura

```
n8n (Docker)  ──SSH──▶  usuario dedicado 'vertiguard'  ──sudo──▶  /opt/vertiguard/*.sh
     │                                                                │
     └──────────────── parsea JSON, compara estado ◀──────────────────┘
                                   │
                                   ▼
                          bot de Telegram  ──▶  tú
```

n8n en Docker no ve el `systemctl`/`docker` del host, así que los chequeos van por SSH como un
**usuario dedicado de privilegios mínimos** (`vertiguard`) que solo puede ejecutar `/opt/vertiguard/*.sh`
gracias a una regla sudoers acotada. Los scripts devuelven JSON; el nodo Code del workflow lo compara
con el estado anterior (guardado en el static data del workflow) y te avisa **solo si cambia**.

> ⚠️ **Persistencia de estado:** n8n solo guarda el `staticData` con el workflow **activo (publicado)**,
> no en ejecuciones manuales de prueba. Activa el workflow para que funcione el "solo si cambia".

---

## Puesta en marcha

### 1. Instalar en el VPS (como root)

```bash
git clone https://github.com/<tu-usuario>/vertice-automations.git
cd vertice-automations/templates/vertiguard-vps-monitoring/scripts
sudo ./install.sh
```

`install.sh` crea el usuario `vertiguard`, instala los scripts en `/opt/vertiguard/`, añade la regla
sudoers acotada, genera una clave SSH dedicada e imprime la **clave privada** al final — cópiala en la
credencial SSH de n8n.

Configurable por entorno, p. ej.:

```bash
sudo VG_USER=monitor N8N_CONTAINER=mi-n8n ./install.sh
```

### 2. Crear credenciales en n8n

| Credencial | Tipo | Notas |
|---|---|---|
| **VPS SSH** | SSH | Host = tu server, usuario = `vertiguard`, auth = *Private Key* (pega la clave del paso 1) |
| **Telegram account** | Telegram API | Token del bot de [@BotFather](https://t.me/BotFather) |

### 3. Importar y configurar cada workflow

1. **Workflows → Import from File** → elige un `*.json`.
2. Asigna las credenciales **VPS SSH** y **Telegram account**.
3. Sustituye **`YOUR_CHAT_ID`** en el nodo de Telegram por tu chat ID
   (lo da [@userinfobot](https://t.me/userinfobot)).
4. En **19-status-on-demand**, pon además `ALLOWED_CHAT_ID` en el nodo Code *Filter /status* para que
   solo tú puedas consultar el server.
5. **Activa** el workflow.

---

## Referencia de configuración

### Placeholders a sustituir (en el JSON del workflow)

| Placeholder | Dónde | Sustitúyelo por |
|---|---|---|
| `YOUR_CHAT_ID` | nodos Telegram | Tu chat ID de Telegram |
| `ALLOWED_CHAT_ID = 0` | WF 19, *Filter /status* | Tu chat ID numérico |
| `example.com` / `n8n.example.com` | etiquetas del nodo Code | Etiquetas cosméticas de tus dominios |
| `REPLACE_ME` | ids de credencial | Se resuelven solos al asignar credenciales |

### Variables de los scripts (override por entorno)

| Variable | Por defecto | Usada por |
|---|---|---|
| `N8N_CONTAINER` | `n8n` | `check_services.sh`, `status.sh` |
| `WEB_MAIN_URL` | `https://example.com` | `check_services.sh`, `status.sh` |
| `WEB_APP_URL` | `https://n8n.example.com/healthz` | `check_services.sh`, `status.sh` |
| `LE_LIVE` | `/etc/letsencrypt/live` | `ssl_check.sh` |
| `BACKUP_REMOTE` | `b2:my-backups` | `backup_watchdog.sh` |
| `BACKUP_PREFIX` | `backup-` | `backup_watchdog.sh` |
| `JAIL` | `sshd` | `fail2ban_report.sh` |

Lo más simple es editar los valores al principio de cada script en `/opt/vertiguard/` tras instalar.

### Umbrales ajustables (en los nodos Code)

- **02 Disco/RAM:** `const TH = 80;` → umbral de aviso en %.
- **03 SSL:** `const TH = 15;` → avisa cuando queden menos de N días.

### Workflow 06 — uptime externo

Es un **webhook**, pensado para un servicio dead-man-switch como
[Healthchecks.io](https://healthchecks.io) (el plan gratis envía webhooks). Apunta el webhook de "caída"
del servicio a la URL de producción del workflow (`/webhook/external-uptime`). El nodo Code ya parsea
los formatos habituales (Healthchecks.io, UptimeRobot, JSON genérico).

---

## Seguridad y privacidad

- El usuario de n8n es **dedicado y de privilegios mínimos**: solo puede ejecutar `/opt/vertiguard/*.sh`
  mediante una regla sudoers acotada — nada más.
- Los scripts son **sondas de solo lectura** (estado, recuentos, días de caducidad). No modifican nada.
- Esta plantilla está **saneada**: sin hosts, IPs, tokens, chat IDs ni claves reales. Las claves y `.env`
  están en `.gitignore`. Publicar la lógica de monitorización no debilita tu server — tus defensas reales
  (claves SSH, fail2ban, firewall) no están aquí.

## Licencia

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
