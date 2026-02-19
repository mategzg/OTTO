# Run Protocol

## Purpose

Estandarizar ejecucion de runs para que el resultado sea reproducible y auditado.

## Use when

- Debes implementar una feature Core/OPS en secuencia de copilot.
- Debes cerrar con evidencia determinista y ledger.

## Avoid when

- Solo necesitas responder una duda conceptual sin cambios.
- No hay root canonico limpio disponible.

## Routing

1. Resolver root: `python3 scripts/repo_root.py` (via funciones expuestas por scripts).
2. Ejecutar cambios in-scope.
3. Entregar cola de notificaciones antes de autonomia: `python3 scripts/outbox_delivery.py --deliver`.
4. Correr gates del run (`pytest -q`, doctor/indexer/hygiene segun objetivo).
5. Persistir: `ops/RUN_LEDGER.ndjson` + `scripts/copilot_report.sh`.

## Maintenance

- Ajustar gates listados cuando cambie policy en `openclaw/CONTEXT_MAP.md`.
- No introducir gates inventados.

## Links

- `ops/RUN_LEDGER.ndjson`
- `scripts/copilot_report.sh`
- `scripts/outbox_delivery.py`
- `brain/cards/openclaw_ops/card_run_ledger.md`
