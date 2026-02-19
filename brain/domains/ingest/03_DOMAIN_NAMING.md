# Domain Naming Rules

## Purpose

Estandarizar a que dominio brain se asimila cada corpus para mantener navegacion consistente.

## Use when

- Se genera plan de ingestion para fuente nueva.

## Avoid when

- Quieres forzar nombres ad-hoc sin heuristica estable.

## Routing

- Si keywords incluyen `openclaw|otto|repo|root|hygiene|quarantine|router` -> dominio `openclaw_ops`.
- Si keywords incluyen `prompt|template|style|protocol|guide` -> dominio `ingest_patterns`.
- Si no hay señal clara -> dominio `external_ingest`.

## Maintenance

- Guardar heuristicas en el router script para reproducibilidad.
- Evitar renombrados de dominio salvo migracion explicita.

## Links

- `scripts/corpus_triage.py`
- `scripts/brain_ingest_router.py`
