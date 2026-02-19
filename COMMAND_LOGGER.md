# COMMAND LOGGER

Formato EXACTO para append en `logs/activity.ndjson`:

```json
{"ts":"ISO8601Z","level":"info","event":"...","detail":"...","task_id":"...","channel":"telegram|whatsapp|manual"}
```

Reglas:

1. Cada comando/hito relevante debe crear una linea.
2. Nunca incluir secretos/tokens.
3. Usar `level` coherente (`info`, `warning`, `error`).
4. `task_id` vacio permitido si no aplica, pero preferido cuando exista mision.
