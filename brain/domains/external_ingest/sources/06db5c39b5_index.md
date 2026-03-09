# Source Router: 20260222T162442Z_065f800160:slice_2024-04_442

## Purpose

Nodo router para navegar cards derivadas de un source pending sin leer el corpus completo.

## Use when

- Necesitas respuesta basada en esta fuente concreta.
- Necesitas ubicar rapidamente cards y source refs.

## Avoid when

- Necesitas operacion general de repo (usar openclaw_ops).

## Routing

- Source id: `06db5c39b5`
- Domain target: `external_ingest`
- Category: `brain_knowledge`
- Processed hint: `vault/inbox_raw/_processed/*_06db5c39b5/source/`
- Cards derivadas:
  - `brain/cards/external_ingest/card_06db5c39b5_01.md`

## Maintenance

- Regenerar con nuevo plan si cambia el source hash.

## Links

- `/home/agente/otto-workspace/vault/inbox_raw/sources/20260222T162442Z_065f800160/normalized/slices/slice_2024-04_442.ndjson`
