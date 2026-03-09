# SPEC-004 M5: Odoo deterministic flow + Lobster handoff gate

Status: READY_FOR_PR
Milestone: M5
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] Workflow determinista con handoff técnico `AwaitApproval`.
- [x] Idempotency key estable por entidad (`lead_quote_order`).
- [x] `dry-run` obligatorio antes de side effects.
- [x] Resume con token tipo Lobster (`lobster:<lead>:<key>`).
- [x] Confirmación final imposible sin aprobación + resumeToken válido.
- [x] Circuit breaker check para flujo Odoo.

## Required tests/gates
- `pytest -q tests/test_spec004_m5_odoo_workflow.py tests/test_circuit_breaker.py`
  - Resultado: `6 passed`
  - Evidencia: `audit/M5/pytest_m5.txt`

## Evidence artifacts
- `audit/M5/dry_run.json`
- `audit/M5/await_approval.json`
- `audit/M5/invalid_resume.json`
- `audit/M5/completed.json`
- `audit/M5/odoo_traces.ndjson`
- `audit/M5/traces_complete.json`
- `audit/M5/commands.ndjson`
- `audit/M5/hashes.sha256`

## Rollback
- Revert commit(s) de `spec004/m5`.
- Eliminar `scripts/odoo_workflow.py` y tests asociados.
