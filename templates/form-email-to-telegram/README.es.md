# Formulario de contacto (email) → Telegram

Recibe un aviso instantáneo en **Telegram** cada vez que alguien rellena el formulario de contacto de
tu web — **sin tocar el código de la web**. El formulario ya te manda un correo; este workflow vigila
ese buzón por **IMAP** y te avisa en cuanto llega un correo que coincide.

> 🇬🇧 [English version](README.md)

Ideal cuando tu web (Laravel, WordPress, un servicio de formularios, lo que sea) envía los envíos a un
buzón pero no quieres meter un webhook dentro de la propia web.

---

## Cómo funciona

```
Formulario de contacto de la web
   │  (manda un correo a tu buzón)
   ▼
Buzón IMAP ─▶ ¿Es del formulario? ─▶ Formatear aviso ─▶ Avisar a Telegram
(solo correo       (filtro por             (remitente +        (a tu chat)
 nuevo que coincide) asunto, red de seguridad) asunto + cuerpo)
```

- El disparador **IMAP** solo trae correo **no leído** cuyo asunto contenga tu palabra clave
  (`["UNSEEN", ["SUBJECT", "SUBJECT_KEYWORD"]]`), así ignora todo lo demás del buzón.
- Un nodo **Filter** revuelve el asunto como red de seguridad.
- Un nodo **Code** arma un mensaje limpio en texto plano (remitente, asunto, cuerpo).
- Un nodo **Telegram** lo envía a tu chat. El disparador es IMAP, no Telegram, así que **no** gasta
  el único trigger activo que admite un bot — puedes reutilizar cualquier bot que ya tengas.
- El correo que coincide se marca como **leído** tras procesarlo, así nunca te avisa dos veces.

Un solo workflow:

| Archivo | Función |
|---|---|
| [`workflows/form-email-to-telegram.json`](workflows/form-email-to-telegram.json) | IMAP → filtro → formatea → Telegram |

Sale **inactivo** (`"active": false`).

---

## Puesta en marcha

### 1. Crea una credencial IMAP en n8n

**Credentials → IMAP**, con los datos de tu proveedor de correo. Por ejemplo (IONOS):

| Campo | Valor |
|---|---|
| Host | `imap.tu-proveedor.com` (IONOS: `imap.ionos.es`) |
| Puerto | `993` |
| SSL/TLS | activado |
| Usuario | el buzón que recibe los correos del formulario |
| Contraseña | la contraseña de ese buzón |

### 2. Importa el workflow

n8n → **Workflows → Import from File** → `workflows/form-email-to-telegram.json`.

### 3. Sustituye los placeholders

| Placeholder | Dónde | Sustituir por |
|---|---|---|
| `SUBJECT_KEYWORD` | **IMAP mailbox** (`customEmailConfig`) **y** **Is it a form email?** (Filter) | Una palabra que aparezca siempre en el asunto de tus correos de formulario (p. ej. `Contacto`, `Nuevo contacto`) |
| `YOUR_CHAT_ID` | **Notify Telegram** | Tu chat id numérico de Telegram (con [@userinfobot](https://t.me/userinfobot)) |
| `REPLACE_ME` (ids de credencial) | nodos IMAP + Telegram | Se resuelve solo al asignar las credenciales |

### 4. Asigna credenciales y activa

Asigna el nodo **IMAP** a tu credencial de buzón y el nodo **Telegram** a tu credencial de bot, y
**activa** el workflow. Rellena el formulario una vez para probar.

---

## Endurecimiento (opcional, recomendado)

En vez de vigilar `INBOX`, crea una **regla en tu proveedor de correo** que mueva los correos del
formulario a una carpeta dedicada (p. ej. `Leads`), y pon el `mailbox` del nodo IMAP a esa carpeta.
Así el workflow nunca toca tu bandeja principal y el filtro por asunto pasa a ser opcional.

---

## Notas

- El aviso se envía en **texto plano** (sin `parse_mode`) a propósito, para que el contenido del
  formulario con `_` o `*` no rompa el formato Markdown de Telegram.
- Los envíos largos se recortan a ~1500 caracteres.
- Funciona con cualquier proveedor con IMAP (IONOS, Gmail, Zoho, Fastmail, tu propio servidor…).

## Seguridad

- **Saneado** — no hay hosts, buzones, tokens ni chat ids reales en el repo, solo placeholders.
- La contraseña del buzón vive solo en la credencial de n8n, nunca en el JSON del workflow.

## Licencia

[MIT](../../LICENSE) © [Vérticedev](https://verticedev.es)
