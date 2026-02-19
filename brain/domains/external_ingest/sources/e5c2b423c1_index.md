# Source Router: claude_inverse_engineering

## Purpose

Nodo router para navegar cards derivadas de un source pending sin leer el corpus completo.

## Use when

- Necesitas respuesta basada en esta fuente concreta.
- Necesitas ubicar rapidamente cards y source refs.

## Avoid when

- Necesitas operacion general de repo (usar openclaw_ops).

## Routing

- Source id: `e5c2b423c1`
- Domain target: `external_ingest`
- Processed hint: `vault/inbox_raw/_processed/*_e5c2b423c1/source/`
- Cards derivadas:
  - `brain/cards/external_ingest/card_e5c2b423c1_01.md`

## Maintenance

- Regenerar con nuevo plan si cambia el source hash.

## Links

- `/home/agente/otto-workspace/vault/inbox_raw/claude_inverse_engineering`
