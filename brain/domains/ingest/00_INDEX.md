# Ingest Domain Index

## Purpose

Hub universal para enrutar ingestion de corpus crudo hacia nodos brain y cards atomicas.

## Use when

- Entra un corpus en `vault/inbox_raw/` y necesitas convertirlo a conocimiento ruteable.
- Necesitas pipeline triage -> plan -> apply -> processed -> reindex.

## Avoid when

- Se pretende copiar dumps crudos directamente a `brain/**`.
- El trabajo es una consulta puntual que ya existe en nodos activos.

## Routing

- Clasificar corpus pendiente -> `brain/domains/ingest/02_PIPELINE.md`
- Nombrar dominio target -> `brain/domains/ingest/03_DOMAIN_NAMING.md`
- Aplicar limites de split -> `brain/domains/ingest/04_SPLIT_HEURISTICS.md`
- Politica pending->processed -> `brain/domains/ingest/05_PENDING_POLICY.md`
- Politica de destino de escritura -> `brain/domains/ingest/06_WRITE_ROUTER.md`
- Operacion de runs/hook/gates -> `brain/domains/openclaw_ops/00_INDEX.md`

## Maintenance

- Mantener rutas y comandos sincronizados con `scripts/corpus_triage.py` y `scripts/brain_ingest_router.py`.
- Actualizar cuando cambie policy de exclusiones en hygiene/indexer.

## Links

- `brain/domains/ingest/01_ROUTER.md`
- `brain/domains/openclaw_ops/00_INDEX.md`
- `state/workspace_hygiene_policy.json`
