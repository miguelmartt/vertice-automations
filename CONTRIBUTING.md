# Contributing

Thanks for your interest! / ¡Gracias por tu interés!

## 🇬🇧 English

1. **One template per folder** under `templates/<name>/` with its own `README.md`.
2. **Sanitize everything.** No real hosts, IPs, tokens, chat IDs, emails, bucket names, or keys.
   Use placeholders (`YOUR_CHAT_ID`, `example.com`, `REPLACE_ME`, …) and configurable variables.
3. **Ship workflows inactive** — `"active": false` in the exported JSON.
4. **No secrets, ever.** Keys, `.env`, and credential files are git-ignored; keep it that way.
5. Open a PR describing what the template does and which credentials it needs.

Before committing, run a quick self-check for leaks:

```bash
grep -rEn '([0-9]{1,3}\.){3}[0-9]{1,3}|[0-9]{8,}|BEGIN .*PRIVATE KEY' templates/ scripts/
```

## 🇪🇸 Español

1. **Una plantilla por carpeta** en `templates/<nombre>/` con su propio `README.md`.
2. **Sanea todo.** Sin hosts, IPs, tokens, chat IDs, emails, nombres de bucket ni claves reales.
   Usa placeholders (`YOUR_CHAT_ID`, `example.com`, `REPLACE_ME`, …) y variables configurables.
3. **Workflows inactivos** — `"active": false` en el JSON exportado.
4. **Nunca secretos.** Claves, `.env` y ficheros de credenciales están en `.gitignore`; déjalo así.
5. Abre un PR explicando qué hace la plantilla y qué credenciales necesita.

Antes de commitear, revisa fugas rápidamente con el comando de arriba.
