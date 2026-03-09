# SPEC-004 M8: Production QA + final readiness audit

Status: READY_FOR_PR
Milestone: M8
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] Consolidación final de evidencia por milestones M0..M8 (PR inventory).
- [x] Auditoría final con GO/NO-GO explícito.
- [x] Bundle reproducible en `audit/M8/*`.

## Required tests/gates
- Validación de presencia de PRs milestone y evidencia asociada.
- GO/NO-GO emitido explícitamente en `audit/M8/final_readiness_report.json`.

## Evidence artifacts
- `audit/M8/pr_inventory.json`
- `audit/M8/final_readiness_report.json`
- `audit/M8/commands.ndjson`
- `audit/M8/hashes.sha256`

## Rollback
- Revert commit(s) de `spec004/m8`.
