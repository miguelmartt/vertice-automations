# VertiGuard — monitorización del VPS y un bot de Telegram

VertiGuard vigila un servidor Linux propio a través de **un solo bot de Telegram**: te avisa **solo
cuando algo cambia**, te manda un **parte diario** con todo lo que importa y atiende **comandos** y un
panel de botones para consultar el servidor y hacer unas pocas acciones seguras desde el móvil.

Es un servicio pequeño de Python (solo librería estándar, nada que instalar con `pip`) más unos
cuantos scripts de root a los que llama mediante una regla de `sudo` muy acotada.

> 🇬🇧 [English version](README.md)

---

## Qué hace

**Avisos cuando algo cambia**, en los dos sentidos (cuando falla y cuando vuelve), sin repetirse:

| Comprobación | Cuándo |
|---|---|
| Servicios (unidades de systemd) y webs (HTTP 2xx/3xx) | cada 5 min |
| Disco(s) y RAM por encima de un umbral (80 % por defecto) | cada hora |
| Certificados de Let's Encrypt a punto de caducar (15 días por defecto) | cada día |
| La copia de hoy en un remoto de rclone | cada día, 06:00 |
| Una comprobación que no puede ejecutarse (falla un script, se agota el tiempo…) | al empezar a fallar y al volver a funcionar |

**Parte diario** (a las 09:00 por defecto), un solo mensaje con:

- un semáforo general: 🟢 todo en orden, 🟡 avisos o 🔴 incidencias, con el motivo;
- servicios y webs, con su tiempo de respuesta;
- CPU, RAM y disco con barras, carga y tiempo encendido;
- seguridad de las últimas 24 h: IPs bloqueadas por fail2ban, baneos nuevos, intentos fallidos de SSH, accesos SSH y el último;
- la copia de hoy con su tamaño y cuántas hay guardadas;
- certificados (el que antes caduca) y contenedores de Docker con su memoria;
- actualizaciones pendientes, cuántas son de seguridad y si hace falta reiniciar para aplicar lo instalado.

Lleva los botones 🔄 *Actualizar* y 📋 *Menú*.

**Comandos**, registrados en el menú «/» de Telegram (con `LANGUAGE=es` salen en español; los nombres en inglés también funcionan):

| Comando | Muestra |
|---|---|
| `/parte` | el parte completo, ahora |
| `/servicios` | cada servicio y web, con tiempos de respuesta |
| `/recursos` | CPU, RAM, swap, cada disco, carga, tiempo encendido, sistema y los procesos que más memoria usan |
| `/seguridad` | fail2ban (ahora, 24 h y total), accesos SSH e intentos fallidos, últimos accesos e IPs bloqueadas |
| `/copias` | la copia de hoy y las últimas, con tamaño y fecha |
| `/ssl` | cada certificado, días que le quedan y fecha de caducidad |
| `/docker` | contenedores, estado, CPU y memoria |
| `/actualizaciones` | paquetes pendientes, de seguridad, si hay que reiniciar y cómo instalarlos |
| `/menu` | un panel de botones que abre cada sección en el mismo mensaje |
| `/reiniciar` | reiniciar uno de los servicios que permitas, tras confirmar |
| `/desbanear` | sacar una IP de fail2ban |
| `/ayuda` | todo lo anterior |

Cualquier otro mensaje va a **Gemini** (opcional), que puede leer el estado del servidor en directo
pero no puede cambiar nada. El bot solo te atiende a ti, en tu chat privado con él (nunca en un grupo).
Los avisos de **UptimeRobot** también pueden llegar por él.

Todos los mensajes están en inglés y en español (`LANGUAGE=en|es`).

---

## Cómo funciona

```
/opt/vertiguard/app/vertiguard.py  (usuario: vertiguard, systemd: vertiguard.service)
 ├─ alerts       planificador → sudo /opt/vertiguard/<sonda>.sh → JSON → Telegram si ha cambiado; parte diario
 ├─ bot          long polling de Telegram → comandos, botones (editan el mismo mensaje), Gemini → sondas
 └─ uptimerobot  http://127.0.0.1:<puerto>/<ruta> ← nginx ← UptimeRobot
```

- Las **sondas** (`/opt/vertiguard/*.sh`) leen el servidor y escriben una línea de JSON: servicios,
  sistema, certificados, fail2ban, accesos SSH, copias, Docker y actualizaciones. Corren como root
  gracias a una sola regla de sudoers, `/etc/sudoers.d/vertiguard`, que nombra cada sonda: las de solo
  lectura solo se pueden lanzar sin argumentos, y `restart_service.sh` y `unban_ip.sh`, con el que ellas
  mismas comprueban. sudo las arranca con un entorno limpio y un `PATH` fijo. El usuario del servicio
  puede ejecutar esos scripts y nada más. Varias se lanzan en paralelo, así que un comando contesta en
  un segundo o dos; la de actualizaciones es lenta y se guarda 6 horas (*Actualizar* la fuerza).
- Las sondas no se fían de lo que leen: los números de `df`, `ps` y compañía se comprueban antes de
  operar con ellos, los caracteres de control nunca llegan al JSON, las listas de `probes.conf` nunca se
  expanden como nombres de fichero y los accesos SSH solo salen de lo que registró el propio servicio SSH.
- Lo que miran las sondas se configura en `/etc/vertiguard/probes.conf`. Se carga como root, así que
  las sondas se niegan a ejecutarse si ese fichero (o su carpeta) no es de root o lo puede escribir
  otro usuario.
- Solo dos acciones cambian algo: `restart_service.sh` (solo las unidades de `RESTARTABLE`) y
  `unban_ip.sh` (valida la IP). El bot siempre pregunta antes de reiniciar.
- El bot usa **long polling**: sin webhook y sin abrir puertos para Telegram. El webhook de
  UptimeRobot escucha solo en `127.0.0.1` y solo acepta peticiones que traigan `WEBHOOK_TOKEN`.
- La unidad de systemd añade el endurecimiento que sigue dejando funcionar a sudo (`PrivateTmp`,
  `ProtectSystem=full`, `UMask=0077`, límites de memoria y de tareas); sus comentarios explican qué se
  queda fuera y por qué.
- Lo último que se avisó se guarda en `/var/lib/vertiguard/state.json`, para no repetir avisos tras
  un reinicio. Los logs van al journal: `journalctl -u vertiguard`.

---

## Requisitos

- Linux con systemd, `sudo`, `curl`, `openssl` y **Python 3.9+** (lo traen AlmaLinux/RHEL 9,
  Debian 11+ y Ubuntu 22.04+).
- Opcional, cada uno añade su parte al parte: fail2ban, rclone (copias), Let's Encrypt, Docker,
  journald (accesos SSH), dnf o apt (actualizaciones), una clave de Google AI Studio (Gemini) y una
  cuenta de UptimeRobot.
- Un bot de Telegram creado con [@BotFather](https://t.me/BotFather) y tu chat ID (pregúntaselo a
  [@userinfobot](https://t.me/userinfobot)).

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
   | `TELEGRAM_CHAT_ID` | tu ID de usuario de Telegram; ahí llega todo y el bot solo te responde a ti, en tu chat privado con él |
   | `BOT_TOKEN` | el bot: avisos, parte, comandos y botones |
   | `COMMANDS` | `off` = el bot solo manda avisos y el parte |
   | `SERVER_NAME` | nombre que sale en los mensajes (por defecto, el hostname) |
   | `GEMINI_API_KEY`, `GEMINI_MODEL` | sin clave, solo comandos y botones |
   | `WEBHOOK_PORT`, `WEBHOOK_PATH`, `WEBHOOK_TOKEN` | webhook de UptimeRobot en `127.0.0.1`; puerto vacío = apagado, y sin un token de 16 caracteres o más no arranca |
   | `LANGUAGE`, `TIMEZONE` | `en`/`es`; zona horaria del parte y de las horas que se muestran |
   | `REPORT_HOUR` | hora del parte diario (0-23), u `off` |
   | `BACKUP_CHECK_HOUR`, `RESOURCE_ALERT_PCT`, `SSL_ALERT_DAYS` | hora de revisar copias y umbrales |

3. **Prueba una sonda** como el usuario del servicio y arráncalo:

   ```bash
   sudo -u vertiguard sudo -n /opt/vertiguard/system.sh
   sudo systemctl enable --now vertiguard
   journalctl -u vertiguard -f
   ```

   El log dice qué partes están en marcha (`alerts, bot, uptimerobot`). Abre el bot en Telegram, manda
   `/menu` y escribe `/` para ver todos los comandos.

### UptimeRobot (opcional)

Lo más sencillo y lo más seguro es no exponer nada: añade en el propio UptimeRobot un contacto de alerta
de tipo **Telegram** y deja `WEBHOOK_PORT` vacío. Si quieres que sus avisos lleguen a través de VertiGuard:

1. En `vertiguard.env`, pon `WEBHOOK_PORT` (por ejemplo `5678`), una `WEBHOOK_PATH` difícil de adivinar y
   un `WEBHOOK_TOKEN` (créalo con `openssl rand -hex 32`). Sin token, el webhook no arranca y el log lo dice.
2. Pon delante un proxy inverso que solo deje pasar `POST` a esa ruta exacta. En nginx, mejor en un
   bloque `server` propio (un subdominio solo para esto):

   ```nginx
   server {
       server_name hooks.example.com;
       # listen 443 ssl; más tu certificado, como en tus otros bloques server
       location = /webhook/uptimerobot {
           limit_except POST { deny all; }
           client_max_body_size 64k;
           proxy_pass http://127.0.0.1:5678;
       }
       location / { return 404; }
   }
   ```

   En el bloque `server` de una web que ya tengas, añade solo el bloque `location = …`.
3. En UptimeRobot, añade un contacto de alerta de tipo **Webhook**, URL
   `https://hooks.example.com/<WEBHOOK_PATH>`, *Send as JSON*, con este *POST value* (tu token en lugar
   de `YOUR_WEBHOOK_TOKEN`):

   ```json
   {"token": "YOUR_WEBHOOK_TOKEN", "monitorFriendlyName": "*monitorFriendlyName*", "monitorURL": "*monitorURL*",
    "alertType": "*alertType*", "alertDetails": "*alertDetails*", "alertDateTime": "*alertDateTime*"}
   ```

   El token también vale como `?token=` en la URL o en una cabecera `X-Webhook-Token`, pero en el cuerpo
   no acaba en el log de accesos del servidor web.

Una petición sin el token correcto recibe un 404, igual que cualquier otra ruta o un `GET`, y no se
envía nada. Los cuerpos de más de 64 KiB se rechazan, y a Telegram llegan como mucho 20 avisos por
minuto: el resto se cuenta y se resume en un solo mensaje al acabar ese minuto.

---

## Actualizar y desinstalar

```bash
cd vertice-automations && git pull && sudo bash templates/vertiguard/install.sh   # conserva tu configuración
```

Si vienes de la primera versión en Python (dos bots): `ALERTS_BOT_TOKEN` se sigue leyendo como
`BOT_TOKEN` y `DEVOPS_BOT_TOKEN` ya no se usa, porque los comandos viven ahora en el mismo bot que los
avisos.

Si vienes de una versión anterior al endurecimiento del 2026-10-31: el instalador reescribe la regla de
sudoers y la unidad, y reinicia el servicio. Si usas el webhook de UptimeRobot, añade `WEBHOOK_TOKEN` y
el token al *POST value* de UptimeRobot (mira arriba), o el webhook no arrancará. Los comandos ya solo
funcionan en tu chat privado con el bot, no en grupos.

Para quitarlo: `systemctl disable --now vertiguard` y borra `/etc/systemd/system/vertiguard.service`,
`/etc/sudoers.d/vertiguard`, `/opt/vertiguard`, `/etc/vertiguard`, `/var/lib/vertiguard` y el usuario.

## Si vienes de la versión de n8n

Los flujos de n8n siguen en la etiqueta [`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final).
Las sondas y la regla de sudoers son la misma idea, así que el cambio consiste en parar los flujos de
n8n, ejecutar el instalador, rellenar los dos ficheros de configuración y arrancar el servicio. El
bot quita solo el webhook que n8n le había puesto. Después, borra la clave SSH con la que n8n entraba
como `vertiguard`: ya no la necesita nadie.

## Tests

```bash
cd templates/vertiguard && python3 -m unittest discover -s tests -t .
```
