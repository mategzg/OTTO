# Hooks And Commands

## Purpose

Mapear comandos de control Telegram-first/fallback para operacion rapida.

## Use when

- Necesitas operar sin terminal directa.
- Necesitas obtener resumen y evidencia de doctor/hygiene.

## Avoid when

- Telegram no esta disponible y se requiere accion destructiva (no permitida).

## Routing

- Raiz y realidad: `/repo roots`, `/repo setroot <id>`, `/repo doctor`, `/repo fix`
- Hygiene workspace: `/repo hygiene`, `/repo clean`
- Hygiene home: `/home hygiene`, `/home clean`
- Ingest brain: `/brain triage`, `/brain plan`, `/brain apply <plan_id>`, `/brain status`
- Autonomia: `/autonomy status`, `/autonomy run`, `/autonomy pause <hours>`, `/autonomy resume`, `/autonomy last`
- Instruction surface: `/context surface`, `/context fix`, `/context status`
- Outbox fallback: `docs/_inbox/outbox_latest.md`

## Maintenance

- Comandos deben permanecer sincronizados con `scripts/openclaw_hook.py`.
- Cambios de mensajes deben conservar rutas de evidencia en salida.

## Links

- `scripts/openclaw_hook.py`
- `docs/_inbox/outbox_latest.md`
- `brain/cards/openclaw_ops/card_hook_commands.md`
