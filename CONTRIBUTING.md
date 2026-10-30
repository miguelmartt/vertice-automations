# Contributing

Thanks for your interest! / ¡Gracias por tu interés!

## 🇬🇧 English

Every template is a small Python service that lives on your server. No automation platform, no
extra dependencies.

1. **One template per folder** under `templates/<name>/`, self-contained:

   | Path | What goes there |
   |---|---|
   | `app/` | Python **3.9+**, **standard library only** (stock AlmaLinux 9 / Debian 11 can run it without `pip`). One entry point in `app/` (e.g. `app/vertiguard.py`) that takes the config file path as its only argument. |
   | `app/config.py`, `telegram.py`, `scheduler.py`, `state.py`, `gemini.py` | **Shared modules**, identical copies of the ones in `templates/vertiguard/app/`. Change them there first and copy them over; CI fails if the copies differ. A template only ships the shared modules it uses. |
   | `app/messages.py` | Every text a user reads, in English and Spanish (`LANGUAGE=en` or `es`, default `en`). |
   | `tests/` | `unittest`, **no network**: fake Telegram, HTTP and the clock. |
   | `systemd/<name>.service` | Runs as a dedicated system user, `Restart=always`, `StateDirectory=<name>`. |
   | `<name>.env.example` | Every setting, commented, with placeholders only. Installed as `/etc/<name>/<name>.env`. |
   | `install.sh` | Idempotent installer (run as root): user, code in `/opt/<name>`, config in `/etc/<name>` (**never overwrites an existing config**), the systemd unit. It does not start the service; the README says how. Re-running it updates the code. |
   | `README.md` + `README.es.md` | What it does, setup step by step, every setting, how to test it. |

2. **How a template behaves**
   - Scheduled jobs use `scheduler.Scheduler`. When a job starts failing it says so on Telegram, and
     again when it recovers — once per change, never on every run.
   - Telegram bots use **long polling** (no webhooks, no open ports) and only answer the configured
     chat ID.
   - Anything that should not be repeated after a restart (last alert sent, processed items) goes in
     `state.State`, under `/var/lib/<name>/`.
   - Logs go to stdout; systemd sends them to the journal (`journalctl -u <name>`).
   - Secrets live only in `/etc/<name>/<name>.env` (mode `640`, `root:<user>`), never in the repo.
3. **Sanitize everything.** No real hosts, IPs, tokens, chat IDs, emails, bucket names or keys. Use
   placeholders (`YOUR_CHAT_ID`, `example.com`, `REPLACE_ME`, …).
4. Open a PR describing what the template does and which accounts or keys it needs.

Before committing:

```bash
for t in templates/*/; do python3 -m unittest discover -s "$t/tests" -t "$t"; done
grep -rEn '([0-9]{1,3}\.){3}[0-9]{1,3}|[0-9]{8,}|BEGIN .*PRIVATE KEY' templates/
```

The leak check flags version numbers and test fixtures too; just make sure nothing real is there.

## 🇪🇸 Español

Cada plantilla es un servicio pequeño en Python que vive en tu servidor. Sin plataforma de
automatización y sin dependencias extra.

1. **Una plantilla por carpeta** en `templates/<nombre>/`, autocontenida:
   - `app/`: Python **3.9+**, **solo librería estándar**. Un punto de entrada en `app/` (por ejemplo
     `app/vertiguard.py`) que recibe la ruta del fichero de configuración como único argumento.
   - `config.py`, `telegram.py`, `scheduler.py`, `state.py`, `gemini.py`: **módulos compartidos**, copias
     idénticas de los de `templates/vertiguard/app/`. Se cambian primero allí y se copian; la CI falla si
     difieren. Cada plantilla lleva solo los que usa.
   - `app/messages.py`: todos los textos que lee una persona, en inglés y en español (`LANGUAGE=en` o
     `es`; por defecto `en`).
   - `tests/`: `unittest`, **sin red**: Telegram, HTTP y el reloj, falsos.
   - `systemd/<nombre>.service`, `<nombre>.env.example`, `install.sh` idempotente (nunca pisa una
     configuración existente) y `README.md` + `README.es.md`.
2. **Cómo se comporta**: los trabajos programados usan `scheduler.Scheduler` y avisan por Telegram al
   empezar a fallar y al recuperarse (una vez por cambio); los bots usan long polling y solo atienden
   al chat configurado; lo que no debe repetirse tras un reinicio va en `state.State`; los logs, a
   stdout; los secretos, solo en `/etc/<nombre>/<nombre>.env`.
3. **Sanea todo**: sin hosts, IPs, tokens, chat IDs, emails, buckets ni claves reales.
4. Abre un PR explicando qué hace la plantilla y qué cuentas o claves necesita.

Antes de commitear, ejecuta los tests y la revisión de fugas de arriba.
