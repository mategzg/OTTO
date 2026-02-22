# SPEC-003 Pre-Integration Baseline

- Commit base: `f71d295`
- Working tree dirty entries: `1410`
- Runtime: Python `3.10.12` | Node `v22.22.0`
- SPEC-003 milestones: `M0..M7 => DONE`
- Focused regression suite: `PASS` (17 tests)

## Critical entrypoints to preserve during integration
- `scripts/nl_skill_router.py::run_nl_router`
- `scripts/retrieval_service.py::retrieve`
- `scripts/evidence_guard.py::build_and_validate`
- `scripts/circuit_breaker.py::should_allow`
- `scripts/heartbeat_worker.py::run_heartbeat_once`
- `scripts/day2_doc_inventory.py::run_day2_inventory_sync`
- `scripts/golden_regression_runner.py::run_golden_regression`
- `scripts/golden_regression_gate.py::run_gate`
- `scripts/release_audit.py::run_release_audit`

## Integration safety rules (locked)
1. No blind merge from external design.
2. Integrate by phase with hard gates.
3. Every phase must add/adjust tests.
4. Keep rollback path and compatibility adapter.

## Next phases we can continue now (without external design)
1. Pre-integration freeze branch + compatibility matrix.
2. Contract tests for router/retrieval/evidence outputs.
3. Migration checklist for `state/*` policies.
4. Runtime checklist for heartbeat + event-driven ingestion trigger seam.
