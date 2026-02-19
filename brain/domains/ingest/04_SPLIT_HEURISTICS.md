# Split Heuristics

## Purpose

Controlar tamano de nodos/cards para mantener respuestas de bajo costo.

## Use when

- El plan detecta corpus grande o heterogeneo.

## Avoid when

- El source es pequeno y cabe en un nodo/card corto.

## Routing

- Limite nodo: aprox 20000 caracteres por archivo.
- Limite card: aprox 3000 caracteres por card.
- Limite referencias por grupo: 40 paths por nodo/card.
- Si source supera limites, crear subnodos/subcards por batch.

## Maintenance

- Ajustar thresholds solo con evidencia de costo/contexto.
- Registrar thresholds en plan para auditoria.

## Links

- `state/ingest_plans/`
- `scripts/brain_ingest_router.py`
