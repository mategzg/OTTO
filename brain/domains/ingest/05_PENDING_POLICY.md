# Pending To Processed Policy

## Purpose

Garantizar que `vault/inbox_raw/` opere como pending queue y tienda a quedar vacio tras apply exitoso.

## Use when

- Se completa apply sin errores.

## Avoid when

- El apply termina partial/blocked.

## Routing

- Source pending: `vault/inbox_raw/<source>`.
- En success: mover a `vault/inbox_raw/_processed/<timestamp>_<source_id>/source/**`.
- Escribir `MANIFEST.json` y `README.md` por snapshot procesado.
- En partial/blocked: no mover pending.

## Maintenance

- No borrar crudo; solo reubicar a processed con trazabilidad.
- Mantener `vault/inbox_raw/**` fuera del indexer brain.

## Links

- `scripts/brain_ingest_router.py`
- `state/workspace_hygiene_policy.json`
- `scripts/brain_index_build.py`
