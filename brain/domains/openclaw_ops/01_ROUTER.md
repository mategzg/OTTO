# OpenClaw Ops Router v1

## Purpose

Definir rutas de bajo costo para responder preguntas operativas sin leer todo el repo.

## Use when

- Debes elegir rapidamente la fuente minima para responder.
- Debes evitar exploracion masiva de `vault/`, tooling o historico irrelevante.

## Avoid when

- La solicitud exige implementacion de producto fuera de OpenClaw Ops.
- La respuesta depende de datos externos no presentes en el repo.

## Routing

- Si incluye "run", "gates", "ledger", "copilot_report" -> ir a `02_RUN_PROTOCOL.md` + card `card_run_ledger.md`.
- Si incluye "root", "nested", "ghost", "quarantine", "salvage" -> ir a `03_REPO_REALITY.md` + card `card_repo_reality_controls.md`.
- Si incluye "hygiene", "junk", "sensitive", "home clean" -> ir a `04_WORKSPACE_HYGIENE.md` + card `card_hygiene_policy.md`.
- Si incluye "hook", "telegram", "/repo", "/home" -> ir a `05_HOOKS_COMMANDS.md` + card `card_hook_commands.md`.
- Si incluye "index", "brain registry", "no indexar vault/tooling" -> ir a card `card_indexer_behavior.md`.

## Maintenance

- Mantener coincidencia con comandos reales en `scripts/openclaw_hook.py`.
- Añadir nuevas rutas solo con evidencia en cards.

## Links

- `brain/domains/openclaw_ops/00_INDEX.md`
- `brain/cards/openclaw_ops/card_hook_commands.md`
- `brain/cards/openclaw_ops/card_indexer_behavior.md`
