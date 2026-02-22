# SPEC-004 M7: Day-2 autonomy heartbeat/cron/breaker

Status: READY_FOR_PR
Milestone: M7
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] Heartbeat behavior no-spam (`HEARTBEAT_OK` cuando no hay alertas) en `scripts/day2_autonomy.py`.
- [x] Cron session aislada por convención `cron:<jobId>`.
- [x] Breaker cross-surface verificado (router/tooling/cron_jobs).
- [x] Fault injection para `cron_jobs` con evidencia reproducible.

## Required tests/gates
- `pytest -q tests/test_spec004_m7_day2.py tests/test_circuit_breaker.py`
  - Resultado: `5 passed`
  - Evidencia: `audit/M7/pytest_m7.txt`

## Evidence artifacts
- `audit/M7/fault_injection_run.json`
- `audit/M7/breaker_fault_injection.json`
- `audit/M7/heartbeat_samples.json`
- `audit/M7/breaker_report.json`
- `audit/M7/commands.ndjson`
- `audit/M7/hashes.sha256`

## Rollback
- Revert commit(s) de `spec004/m7`.
- Eliminar `scripts/day2_autonomy.py` y tests asociados.
