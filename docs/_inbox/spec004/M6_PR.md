# SPEC-004 M6: Skills/plugins intake marketplace

Status: READY_FOR_PR
Milestone: M6
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] Skills pack ZIP intake como untrusted (`scripts/skills_intake.py`).
- [x] Validación mínima (`SKILL.md` requerido).
- [x] Static scan básico + `risk_score` y `relevance_score` reproducibles.
- [x] Promoción controlada a `skills/production/*` cuando pasa gates.
- [x] Rollback funcional de última promoción.
- [x] Catálogo snapshot (`state/skills_catalog.json` + `audit/M6/catalog_snapshot.json`).

## Required tests/gates
- `pytest -q tests/test_spec004_m6_skills_intake.py tests/test_skill_recipe_registry.py`
  - Resultado: `6 passed`
  - Evidencia: `audit/M6/pytest_m6.txt`

## Evidence artifacts
- `audit/M6/intake_valid.json`
- `audit/M6/intake_invalid.json`
- `audit/M6/rollback.json`
- `audit/M6/intake_decisions.ndjson`
- `audit/M6/catalog_snapshot.json`
- `audit/M6/commands.ndjson`
- `audit/M6/hashes.sha256`

## Rollback
- Ejecutar rollback de intake (`scripts/skills_intake.py --rollback`).
- Revert commit(s) de `spec004/m6`.
