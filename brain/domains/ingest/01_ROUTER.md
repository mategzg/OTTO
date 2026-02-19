# Universal Ingest Router v1

## Purpose

Reducir costo de contexto: enrutar preguntas de ingestion a nodos y cards en lugar de leer corpus completo.

## Use when

- Preguntas: "que hago con un corpus nuevo", "como lo asimilo", "donde quedo procesado".

## Avoid when

- El corpus no esta en `vault/inbox_raw/`.
- La tarea requiere solo higiene o repo reality sin ingestion.

## Routing

- "quiero diagnosticar que hay pendiente" -> usar `/brain status` o `/brain triage`.
- "quiero preparar cambios sin mutar" -> usar `/brain plan`.
- "quiero aplicar un plan" -> usar `/brain apply <plan_id>`.
- "quiero verificar reglas de split" -> `brain/domains/ingest/04_SPLIT_HEURISTICS.md`.
- "quiero soporte de comandos operativos" -> `brain/domains/openclaw_ops/05_HOOKS_COMMANDS.md`.

## Maintenance

- Mantener comandos y rutas iguales a los subcomandos reales del router.

## Links

- `scripts/openclaw_hook.py`
- `scripts/corpus_triage.py`
- `scripts/brain_ingest_router.py`
