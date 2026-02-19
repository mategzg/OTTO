# Router: external_ingest

## Purpose

Ruta de bajo costo para consultas del dominio asimilado.

## Use when

- Preguntas por contenido incorporado desde `vault/inbox_raw`.

## Avoid when

- Preguntas de operacion repo/hygiene (usar openclaw_ops).

## Routing

- Buscar primero en `sources/*_index.md`.
- Resolver detalle en cards con `source_ref`.
- Solo si falta detalle, abrir snapshot en `_processed`.

## Maintenance

- Mantener rutas compatibles con plan/apply actuales.

## Links

- `brain/domains/openclaw_ops/01_ROUTER.md`
- `vault/inbox_raw/_processed/`
