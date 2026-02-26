# SPEC-004 M4: SharePoint incremental sync + audience tagging

Status: READY_FOR_PR
Milestone: M4
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] Sync incremental con delta token persistido (`scripts/sharepoint_sync.py`).
- [x] Rename/delete con tombstones (`state/sharepoint_tombstones.ndjson`).
- [x] Audience tagging en markdown (`<!-- audience: ... -->`) y enforcement en retrieval.
- [x] Rerun incremental idempotente.

## Required tests/gates
- `pytest -q tests/test_spec004_m4_sharepoint_sync.py tests/test_retrieval_hybrid_pipeline.py`
  - Resultado: `5 passed`
  - Evidencia: `audit/M4/pytest_m4.txt`

## Evidence artifacts
- `audit/M4/delta_runs.json`
- `audit/M4/audience_filter_tests.json`
- `audit/M4/sync_run.json`
- `audit/M4/commands.ndjson`
- `audit/M4/hashes.sha256`
- `state/sharepoint_sync_state.json`
- `state/sharepoint_manifest.json`
- `state/sharepoint_tombstones.ndjson`

## Rollback
- Revert commit(s) de `spec004/m4`.
- Eliminar `scripts/sharepoint_sync.py` y restituir estado previo de retrieval audience filter.
