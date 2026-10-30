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
- Cada uno se convierte en un mensaje corto, se manda a tu chat y se **marca como leído**, para que
  nunca te avise dos veces.
- Si le dices qué etiquetas usa tu formulario (`FIELDS=Nombre,Email,Teléfono`), saca esos valores
  (`Nombre: Ana`, o la etiqueta en una línea y el valor en la siguiente). `MESSAGE_START` y
  `MESSAGE_END` recogen el mensaje libre. Sin ellos, te llegan el asunto y el cuerpo.
- Si no puede leer el buzón varias veces seguidas (`FAILURES_BEFORE_ALERT`, 5 por defecto), te lo
  dice una vez, y otra cuando vuelve a funcionar.
- El bot solo envía mensajes, así que puedes reutilizar cualquier bot que ya tengas.

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
`NoNewPrivileges`); solo necesita salir a la red.

## Actualizar

```bash
cd vertice-automations && git pull && sudo bash templates/form-email-to-telegram/install.sh
```

La versión de n8n de esta plantilla sigue en la etiqueta
[`n8n-final`](https://github.com/miguelmartt/vertice-automations/tree/n8n-final).

## Tests

```bash
cd templates/form-email-to-telegram && python3 -m unittest discover -s tests -t .
```
