# VertiGuard — monitorización del VPS y bot DevOps en Telegram

VertiGuard vigila un servidor Linux propio y te avisa por Telegram **solo cuando algo cambia**. Un
bot DevOps te deja consultar el servidor y hacer unas pocas acciones seguras desde el móvil, y los
avisos de UptimeRobot también pueden pasar por él.

Es un servicio pequeño de Python (solo librería estándar, nada que instalar con `pip`) más unos
cuantos scripts de root a los que llama mediante una regla de `sudo` muy acotada.

> 🇬🇧 [English version](README.md)

---

## Qué hace

| Comprobación | Cuándo | Avisa |
|---|---|---|
| Servicios (unidades de systemd) y webs (HTTP 2xx/3xx) | cada 5 min | cuando algo cae o vuelve |
| Disco `/` y RAM por encima de un umbral (80 % por defecto) | cada hora | al cruzar el umbral, en los dos sentidos |
| Certificados de Let's Encrypt a punto de caducar (15 días por defecto) | cada día, 09:00 | cuando uno se acerca y cuando se renueva |
| La copia de hoy en un remoto de rclone | cada día, 06:00 | cuando falta y cuando vuelve |
| Informe de una jail de fail2ban | cada día, 09:00 | siempre (un resumen corto) |
| Actualizaciones pendientes (dnf o apt) | los lunes, 09:00 | siempre |
| Una comprobación que no puede ejecutarse (falla un script, se agota el tiempo…) | — | al empezar a fallar y al volver a funcionar |

**Bot DevOps** (opcional): envía `/menu` y tendrás botones para el estado del servidor, disco, RAM,
uptime, SSL, fail2ban y copias, para reiniciar los servicios que permitas (con un paso de
*Confirmar*) y para desbanear una IP. Cualquier otro mensaje va a **Gemini**, que puede leer el
estado del servidor en directo pero no puede cambiar nada. El bot solo atiende a tu chat.

**Webhook de UptimeRobot** (opcional): un monitor externo detecta lo que el propio servidor no puede
(que se caiga la máquina entera). VertiGuard recibe su webhook y reenvía el aviso al mismo chat.

Todos los mensajes están en inglés y en español (`LANGUAGE=en|es`).

---

## Cómo funciona

```
/opt/vertiguard/app/vertiguard.py  (usuario: vertiguard, systemd: vertiguard.service)
 ├─ alerts       planificador → sudo /opt/vertiguard/<sonda>.sh → JSON → Telegram si ha cambiado
 ├─ bot          long polling de Telegram → botones de /menu o Gemini → sondas
 └─ uptimerobot  http://127.0.0.1:<puerto>/<ruta> ← nginx ← UptimeRobot
```

- Las **sondas** (`/opt/vertiguard/*.sh`) leen el servidor y escriben una línea de JSON. Corren como
  root gracias a una sola regla de sudoers: `vertiguard ALL=(root) NOPASSWD: /opt/vertiguard/*.sh`.
  El usuario del servicio puede ejecutar esos scripts y nada más.
- Lo que miran las sondas se configura en `/etc/vertiguard/probes.conf`. Se carga como root, así que
  las sondas se niegan a ejecutarse si ese fichero (o su carpeta) no es de root o lo puede escribir
  otro usuario.
- Solo dos acciones cambian algo: `restart_service.sh` (solo las unidades de `RESTARTABLE`) y
  `unban_ip.sh` (valida la IP). El bot siempre pide confirmación antes de reiniciar.
- El bot usa **long polling**: sin webhook y sin abrir puertos para Telegram. El webhook de
  UptimeRobot escucha solo en `127.0.0.1`.
- Lo último que se avisó se guarda en `/var/lib/vertiguard/state.json`, para no repetir avisos tras
  un reinicio. Los logs van al journal: `journalctl -u vertiguard`.

---

## Requisitos

- Linux con systemd, `sudo`, `curl`, `openssl` y **Python 3.9+** (lo traen AlmaLinux/RHEL 9,
  Debian 11+ y Ubuntu 22.04+).
- Opcional: fail2ban, rclone (para comprobar las copias), certificados de Let's Encrypt, una clave de
  Google AI Studio (para el chat con Gemini) y una cuenta de UptimeRobot.
- Uno o dos bots de Telegram creados con [@BotFather](https://t.me/BotFather) y tu chat ID
  (pregúntaselo a [@userinfobot](https://t.me/userinfobot)).

---

## Instalación

```bash
git clone https://github.com/miguelmartt/vertice-automations.git
cd vertice-automations
sudo bash templates/vertiguard/install.sh
```

El instalador crea el usuario de sistema `vertiguard`, copia el código a `/opt/vertiguard`, escribe
la regla de sudoers, instala la unidad de systemd y crea los dos ficheros de configuración (nunca los
pisa). Todavía no arranca nada.

1. **Qué vigilar**: edita `/etc/vertiguard/probes.conf`.

   | Ajuste | Ejemplo | Para qué |
   |---|---|---|
   | `SERVICES` | `"nginx mariadb"` | unidades de systemd que tienen que estar en marcha |
   | `URLS` | `"https://example.com"` | webs que tienen que responder 2xx/3xx |
   | `RESTARTABLE` | `"nginx"` | unidades que el bot puede reiniciar (vacío = sin botones de reinicio) |
   | `LE_LIVE` | `"/etc/letsencrypt/live"` | carpeta de los certificados |
   | `BACKUP_REMOTE` / `BACKUP_PREFIX` | `"b2:mis-copias"` / `"backup-"` | remoto:ruta de rclone y prefijo del fichero antes de la fecha; remoto vacío = no se comprueban copias |
   | `JAIL` | `"sshd"` | jail de fail2ban |

2. **Secretos y opciones**: edita `/etc/vertiguard/vertiguard.env`.

   | Ajuste | Para qué |
   |---|---|
   | `TELEGRAM_CHAT_ID` | tu chat ID; ahí llegan los avisos y es el único chat al que responde el bot |
   | `ALERTS_BOT_TOKEN` | bot que manda los avisos |
   | `DEVOPS_BOT_TOKEN` | bot de `/menu` y Gemini; vacío = sin bot DevOps (puede ser el mismo bot) |
   | `GEMINI_API_KEY`, `GEMINI_MODEL` | sin clave, el bot solo ofrece `/menu` |
   | `WEBHOOK_PORT`, `WEBHOOK_PATH` | webhook de UptimeRobot en `127.0.0.1`; puerto vacío = apagado |
   | `LANGUAGE`, `TIMEZONE` | `en`/`es`; zona horaria de los informes diarios |
   | `RESOURCE_ALERT_PCT`, `SSL_ALERT_DAYS`, `REPORT_HOUR`, `BACKUP_CHECK_HOUR` | umbrales y horas |

3. **Prueba una sonda** como el usuario del servicio y arráncalo:

   ```bash
   sudo -u vertiguard sudo -n /opt/vertiguard/check_services.sh
   sudo systemctl enable --now vertiguard
   journalctl -u vertiguard -f
   ```

   El log dice qué partes están en marcha (`alerts, bot, uptimerobot`). Manda `/menu` al bot DevOps.

### UptimeRobot (opcional)

1. Pon `WEBHOOK_PORT` (por ejemplo `5678`) y una `WEBHOOK_PATH` difícil de adivinar en `vertiguard.env`.
2. Pon un proxy inverso delante; por ejemplo, en nginx:

   ```nginx
   location /webhook/ { proxy_pass http://127.0.0.1:5678; }
   ```

3. En UptimeRobot, añade un contacto de alerta de tipo **Webhook**, POST, cuerpo JSON, URL
   `https://tu-dominio/<WEBHOOK_PATH>`, con las variables `*monitorFriendlyName*`, `*monitorURL*`,
   `*alertType*`, `*alertDetails*` y `*alertDateTime*`.

---

## Actualizar y desinstalar

```bash
cd vertice-automations && git pull && sudo bash templates/vertiguard/install.sh   # conserva tu configuración
```

Para quitarlo: `systemctl disable --now vertiguard` y borra `/etc/systemd/system/vertiguard.service`,
`/etc/sudoers.d/vertiguard`, `/opt/vertiguard`, `/etc/vertiguard`, `/var/lib/vertiguard` y el usuario.

## Si vienes de la versión de n8n

Los flujos de n8n siguen en la etiqueta [`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final).
Las sondas y la regla de sudoers son la misma idea, así que el cambio consiste en parar los flujos de
n8n, ejecutar el instalador, rellenar los dos ficheros de configuración y arrancar el servicio. El
bot DevOps quita solo el webhook que n8n le había puesto. Después, borra la clave SSH con la que n8n
entraba como `vertiguard`: ya no la necesita nadie.

## Tests

```bash
cd templates/vertiguard && python3 -m unittest discover -s tests -t .
```
