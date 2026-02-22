# SPEC-004 M2: Hybrid retrieval + evidence contract

Status: READY_FOR_PR
Milestone: M2
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] Audience filter aplicado antes de topK en retrieval (`scripts/retrieval_service.py`).
- [x] AnswerGate universal fortalecido con bloqueo de citas fuera de audiencia (`scripts/evidence_guard.py`).
- [x] Abstención obligatoria (`NO_VERIFICADO + GAPS`) cuando no hay base suficiente.
- [x] Retrieval pack persistido por `trace_id` (`audit/M2/retrieval_packs/<trace>.json`).

## Required tests/gates
- `pytest -q tests/test_spec004_m2_answer_gate.py tests/test_retrieval_hybrid_pipeline.py tests/test_acl_no_leak_candidates.py tests/test_acl_no_leak_citations.py tests/test_nl_skill_router.py`
  - Resultado: `15 passed`
  - Evidencia: `audit/M2/pytest_m2.txt`

## Evidence artifacts
- `audit/M2/evidence_gate_report.json`
- `audit/M2/pytest_m2.txt`
- `audit/M2/commands.ndjson`
- `audit/M2/hashes.sha256`
- `audit/M2/retrieval_packs/`

## Rollback
- Revert commit(s) de `spec004/m2`.
- Restaurar `retrieval_service`, `evidence_guard` y `nl_skill_router` a estado previo.
