# SPEC-004 M3: Event-driven ingestion + _pending immediate trigger

Status: READY_FOR_PR
Milestone: M3
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] Adjuntos clasificados por tipo en intake de chat (`scripts/chat_to_inbox_drop.py`).
- [x] Idempotencia por hash reforzada para ingest (fingerprint por contenido en `scripts/dropbox_intake.py`).
- [x] Trigger inmediato de `_pending` sin heartbeat (`scripts/pending_ingest_trigger.py`).
- [x] Backpressure explícito con `max_entries` + pending remanente.
- [x] QA mínimo post-ingest con test suite específica.

## Required tests/gates
- `pytest -q tests/test_spec004_m3_ingest.py tests/test_chat_to_inbox_drop.py tests/test_dropbox_intake.py`
  - Resultado: `7 passed`
  - Evidencia: `audit/M3/pytest_m3.txt`

## Evidence artifacts
- `audit/M3/ingest_manifest.json`
- `audit/M3/trigger_run.json`
- `audit/M3/pytest_m3.txt`
- `audit/M3/commands.ndjson`
- `audit/M3/hashes.sha256`
- Runtime trigger report: `docs/_inbox/pending_ingest_trigger_latest.json`

## Rollback
- Revert commit(s) de `spec004/m3`.
- Eliminar `scripts/pending_ingest_trigger.py`.
- Restaurar fingerprint previo en `dropbox_intake` y clasificación previa en `chat_to_inbox_drop`.
