# SPEC-004 M1: Delegation-by-default + queue hardening

Status: READY_FOR_PR
Milestone: M1
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] Regla dura `should_delegate()` implementada (`scripts/dispatcher_policy.py`).
- [x] Límites formales de ejecución: `maxConcurrent`, `maxSpawnDepth`, `maxChildrenPerAgent` (`state/dispatcher_policy.json`).
- [x] Señal de dispatcher en runtime report (`actions.dispatcher` en ingress adapter).
- [x] Queue collect bajo carga para ACKs (`outbox_queue.enqueue_message` con `metadata.collect_key`).

## Required tests/gates
- `pytest -q tests/test_spec004_m1_dispatcher.py tests/test_outbox_queue_and_delivery_mock_cli.py`
  - Resultado: `6 passed`
  - Evidencia: `audit/M1/pytest_m1.txt`
- Benchmark burst (60 eventos):
  - `ack p95 < 2s` ✅
  - Evidencia: `audit/M1/benchmark_dispatcher.json`

## Evidence artifacts
- `audit/M1/benchmark_dispatcher.json`
- `audit/M1/pytest_m1.txt`
- `audit/M1/commands.ndjson`
- `audit/M1/hashes.sha256`

## Rollback
- Revert commit(s) de `spec004/m1`.
- Eliminar `scripts/dispatcher_policy.py` y wiring de dispatcher/collect.
- Restaurar comportamiento previo en `outbox_queue` y `channel_ingress_adapter`.
