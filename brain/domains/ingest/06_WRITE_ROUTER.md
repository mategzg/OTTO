# Write Router v1

## Purpose

Definir de forma determinista donde escribe OTTO lo aprendido durante ingestion autonoma.

## Use when

- Hay sources en `vault/inbox_raw/` y necesitas decidir destino final por categoria.
- Quieres auditar por que un source fue a brain, openclaw_ops, memory o templates.

## Avoid when

- Se busca copiar crudo masivo dentro de `brain/**` o `memory/**`.
- El source no paso por triage/plan (primero usar `/brain triage` y `/brain plan`).

## Routing

- Politica canonica: `state/write_router_policy.json`.
- Engine: `scripts/write_router.py`.
- Integracion de apply: `scripts/brain_ingest_router.py`.

Tabla de categoria -> destino:

- `ops_system` -> `brain/domains/openclaw_ops/**` + cards operativas.
- `brain_knowledge` -> `brain/domains/<domain>/**` + `brain/cards/<domain>/**`.
- `memory_human` -> `docs/_inbox/memory_inbox.ndjson` (append-only capture) -> `scripts/memory_compact.py` promueve a `memory/*.ndjson`.
- `templates` -> `brain/templates/**`.
- `inbox_only` -> solo snapshot en `vault/inbox_raw/_processed/**`.
- `ignore` -> snapshot en `vault/inbox_raw/_processed/**` sin derivados.

Guardrail reservado (`AGENTS*` / `CLAUDE*`):

- Si un source trae esos nombres reservados fuera de allowlist, la categoria se fuerza a `inbox_only`.
- Se genera derivado seguro (`card_<source_id>_agents_example.md` o `card_<source_id>_claude_example.md`) sin crear nombres reservados en subdirectorios.

Ejemplos del repo:

- Evidencia de gates/hooks/root/hygiene -> `ops_system` (`openclaw_ops`).
- Conocimiento reusable no operativo -> `brain_knowledge`.
- Decisiones/preferencias humanas -> `memory_human`.
- Patrones de prompt/playbook -> `templates`.

## Maintenance

- No-overwrite: conflictos siempre side-by-side con sufijo `__from_<source_id>`.
- Crudo siempre queda como source snapshot procesado con `MANIFEST.json`.
- Memory canonical solo lo toca el compactor (`scripts/memory_compact.py`), no el ingest apply directo.
- Ajustar reglas solo editando policy y dejando evidencia en reportes.

## Links

- `state/write_router_policy.json`
- `scripts/write_router.py`
- `scripts/brain_ingest_router.py`
- `brain/domains/ingest/02_PIPELINE.md`
- `state/instruction_surface_policy.json`
