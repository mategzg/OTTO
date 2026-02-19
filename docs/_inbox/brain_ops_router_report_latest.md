# Brain Ops Router Report

- Canonical root: `/home/agente/otto-workspace`
- Domain hub: `brain/domains/openclaw_ops/00_INDEX.md`
- Domain nodes: 7
- Cards: 6
- Routes: 5
- Source refs: 14
- Unresolved source refs: 0
- JSON report: `docs/_inbox/brain_ops_router_report_latest.json`
- Log report: `logs/brain_ops_router_latest.json`

## Domain Nodes

- `brain/domains/openclaw_ops/00_INDEX.md`
- `brain/domains/openclaw_ops/01_ROUTER.md`
- `brain/domains/openclaw_ops/02_RUN_PROTOCOL.md`
- `brain/domains/openclaw_ops/03_REPO_REALITY.md`
- `brain/domains/openclaw_ops/04_WORKSPACE_HYGIENE.md`
- `brain/domains/openclaw_ops/05_HOOKS_COMMANDS.md`
- `brain/domains/openclaw_ops/06_PROMPT_ENGINEERING_PATTERNS.md`

## Cards

- `brain/cards/openclaw_ops/card_context_authority.md`
- `brain/cards/openclaw_ops/card_hook_commands.md`
- `brain/cards/openclaw_ops/card_hygiene_policy.md`
- `brain/cards/openclaw_ops/card_indexer_behavior.md`
- `brain/cards/openclaw_ops/card_repo_reality_controls.md`
- `brain/cards/openclaw_ops/card_run_ledger.md`

## Recommended Routes

- - Si incluye "hook", "telegram", "/repo", "/home" -> ir a `05_HOOKS_COMMANDS.md` + card `card_hook_commands.md`.
- - Si incluye "hygiene", "junk", "sensitive", "home clean" -> ir a `04_WORKSPACE_HYGIENE.md` + card `card_hygiene_policy.md`.
- - Si incluye "index", "brain registry", "no indexar vault/tooling" -> ir a card `card_indexer_behavior.md`.
- - Si incluye "root", "nested", "ghost", "quarantine", "salvage" -> ir a `03_REPO_REALITY.md` + card `card_repo_reality_controls.md`.
- - Si incluye "run", "gates", "ledger", "copilot_report" -> ir a `02_RUN_PROTOCOL.md` + card `card_run_ledger.md`.

## Raw Source

- Ingested: true (14 files)
- Target: `vault/inbox_raw/claude_inverse_engineering/20260218T045727Z`
- Manifest: `vault/inbox_raw/claude_inverse_engineering/20260218T045727Z/MANIFEST.json`
- README: `vault/inbox_raw/claude_inverse_engineering/20260218T045727Z/README.md`

## Source Refs

- `brain/cards/openclaw_ops/card_context_authority.md` -> `openclaw/CONTEXT_MAP.md` | exists=True
- `brain/cards/openclaw_ops/card_hook_commands.md` -> `docs/_inbox/outbox_latest.md` | exists=True
- `brain/cards/openclaw_ops/card_hook_commands.md` -> `scripts/openclaw_hook.py` | exists=True
- `brain/cards/openclaw_ops/card_hygiene_policy.md` -> `scripts/home_hygiene_doctor.py` | exists=True
- `brain/cards/openclaw_ops/card_hygiene_policy.md` -> `scripts/workspace_hygiene_doctor.py` | exists=True
- `brain/cards/openclaw_ops/card_hygiene_policy.md` -> `state/workspace_hygiene_policy.json` | exists=True
- `brain/cards/openclaw_ops/card_indexer_behavior.md` -> `scripts/brain_index_build.py` | exists=True
- `brain/cards/openclaw_ops/card_indexer_behavior.md` -> `state/workspace_hygiene_policy.json` | exists=True
- `brain/cards/openclaw_ops/card_repo_reality_controls.md` -> `scripts/repo_reality_doctor.py` | exists=True
- `brain/cards/openclaw_ops/card_repo_reality_controls.md` -> `scripts/repo_root.py` | exists=True
- `brain/cards/openclaw_ops/card_repo_reality_controls.md` -> `state/repo_reality_allowlist.json` | exists=True
- `brain/cards/openclaw_ops/card_repo_reality_controls.md` -> `state/repo_reality_state.json` | exists=True
- `brain/cards/openclaw_ops/card_run_ledger.md` -> `ops/RUN_LEDGER.ndjson` | exists=True
- `brain/cards/openclaw_ops/card_run_ledger.md` -> `scripts/copilot_report.sh` | exists=True
