# Formulario de contacto (email) → Telegram

Recibe un mensaje en **Telegram** en cuanto alguien envía el formulario de contacto de tu web,
**sin tocar el código de la web**. El formulario ya te manda un correo; este servicio pequeño vigila
ese buzón por **IMAP** y reenvía a tu chat cada correo nuevo del formulario.

Python 3.9+, solo librería estándar, gestionado por systemd.

> 🇬🇧 [English version](README.md)

---

## Cómo funciona

```
Formulario web ──correo──▶ tu buzón ◀──IMAP cada 60 s── form-to-telegram ──▶ Telegram
```

- Cada `CHECK_EVERY_SECONDS` busca correos **sin leer** cuyo asunto contenga `SUBJECT_KEYWORD`, así
  que ignora el resto de la bandeja.
- Solo pasan los correos **de tu web**: enviados desde `FORM_FROM` y, por defecto, con una firma DKIM
  de ese dominio que tu servidor de correo ha comprobado (mira [Comprobar el remitente](#comprobar-el-remitente)).
  Cualquiera puede mandarte un correo con el asunto adecuado; así no se cuelan falsos en tu chat.
- Cada uno se convierte en un mensaje corto, se manda a tu chat y se **marca como leído**, para que
  nunca te avise dos veces.
- Si le dices qué etiquetas usa tu formulario (`FIELDS=Nombre,Email,Teléfono`), saca esos valores
  (`Nombre: Ana`, o la etiqueta en una línea y el valor en la siguiente). `MESSAGE_START` y
  `MESSAGE_END` recogen el mensaje libre. Sin ellos, te llegan el asunto y el cuerpo.
- Cada correo se trata por separado, así que uno roto nunca frena a los demás. Uno demasiado grande
  (más de 5 MB, que no llega a descargarse) o que no se puede leer se cambia por un aviso corto con su
  asunto; uno que no viene de tu web se queda fuera, con un mensaje por comprobación que dice cuántos.
  Esos correos siguen sin leer en el buzón con la etiqueta IMAP `$FormFailed`, para no volver a
  descargarlos (en un servidor que no admite etiquetas, se marcan como leídos).
- Como mucho 10 correos por comprobación; el resto llega en la siguiente. Las vistas previas de
  enlaces van desactivadas y, si Telegram pide ir más despacio, espera lo que diga.
- Si no puede leer el buzón varias veces seguidas (`FAILURES_BEFORE_ALERT`, 5 por defecto), te lo
  dice una vez, y otra cuando vuelve a funcionar. Si lo que falla es Telegram, el correo espera a la
  siguiente comprobación.
- Se verifica el certificado del servidor IMAP, y el bot solo envía mensajes, así que puedes
  reutilizar cualquier bot que ya tengas.

Ejemplo de lo que llega:

```
📬 Nuevo contacto de example.com

Nombre: Ana López
Email: ana@example.com
Teléfono: 600 000 000

💬 Mensaje:
Quería presupuesto para una web nueva.
```

---

## Instalación

```bash
git clone https://github.com/miguelmartt/vertice-automations.git
cd vertice-automations
sudo bash templates/form-email-to-telegram/install.sh
```

Después edita `/etc/form-to-telegram/form-to-telegram.env`:

| Ajuste | Para qué |
|---|---|
| `TELEGRAM_CHAT_ID`, `BOT_TOKEN` | tu chat ID ([@userinfobot](https://t.me/userinfobot)) y un bot de [@BotFather](https://t.me/BotFather) |
| `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_FOLDER` | el buzón que recibe los correos del formulario (IMAP con SSL, puerto 993) |
| `SUBJECT_KEYWORD` | texto que llevan en el asunto los correos del formulario (mejor sin tildes ni emojis) |
| `FORM_FROM` | obligatorio: la dirección From con la que tu web manda los correos del formulario; `any` = cualquier remitente (no recomendado) |
| `DKIM_DOMAIN` | el dominio cuya firma DKIM tiene que pasar; vacío = el dominio de `FORM_FROM`, `off` = sin comprobar DKIM |
| `SITE_NAME` | opcional, aparece en el título |
| `FIELDS` | opcional, etiquetas que sacar, separadas por comas y en orden |
| `MESSAGE_START`, `MESSAGE_END` | opcional, líneas donde empieza y acaba el mensaje libre |
| `LANGUAGE` | `en` o `es` |
| `CHECK_EVERY_SECONDS`, `FAILURES_BEFORE_ALERT` | cada cuánto mira y cuándo se queja |

Arráncalo y mándate una prueba desde el formulario:

```bash
sudo systemctl enable --now form-to-telegram
journalctl -u form-to-telegram -f
```

El servicio corre con su propio usuario y con el endurecimiento de systemd (`ProtectSystem=strict`,
`NoNewPrivileges`, sin capacidades, filtro de llamadas al sistema, solo sockets IP y locales…) y con
un tope de 256 MB de memoria y media CPU; solo necesita salir a la red.

### Comprobar el remitente

Abre uno de los correos del formulario en tu cliente de correo y mira su código fuente («Mostrar
original», «Ver código fuente»). La **primera** línea `Authentication-Results:` es la que añadió tu
servidor de correo, y debería decir `dkim=pass` con `header.d=example.com` (o `header.i=@example.com`),
tu dominio. Solo cuenta esa primera: las que haya más abajo venían con el correo y las pudo escribir
quien lo envió.

- Si es así, pon en `FORM_FROM` la dirección del `From:` del correo y deja `DKIM_DOMAIN` vacío (o pon
  el dominio de `header.d` si no es el de `FORM_FROM`).
- Si no hay esa línea, o no pasa, tu web envía sin DKIM. Activa DKIM para tu dominio en tu proveedor de
  correo si puedes; mientras tanto, `DKIM_DOMAIN=off` solo comprueba `FORM_FROM`, que cualquiera puede
  falsificar.

Los correos que no pasan la comprobación siguen sin leer en el buzón, y el bot te dice cuántos se han
quedado fuera.

## Actualizar

```bash
cd vertice-automations && git pull && sudo bash templates/form-email-to-telegram/install.sh
```

Si vienes de una versión anterior al endurecimiento del 2026-10-31: `FORM_FROM` ahora es obligatorio.
Mientras no esté en tu fichero de configuración, el instalador actualiza el código pero no reinicia el
servicio (sigue el antiguo); ponlo, revisa `DKIM_DOMAIN` y ejecuta `systemctl restart form-to-telegram`.

La versión de n8n de esta plantilla sigue en la etiqueta
[`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final).

## Tests

```bash
cd templates/form-email-to-telegram && python3 -m unittest discover -s tests -t .
```
