# HANDOFF — NEW SESSION (SPEC-003 Continuity)

## Contexto de negocio y objetivo superior

Mateo quiere que OTTO sea un sistema operativo personal/profesional (no solo bot), con máxima autonomía y proactividad para ejecutar su visión en vida + SG Acabados.

Puntos clave del owner:
- Comunicación con Mateo: simple, directa, sin jerga técnica innecesaria.
- Operación interna: técnica de élite, robusta y auditable.
- Toda directriz importante se persiste en sistema (no solo contexto conversacional).
- Delegación: evitar coder CLIs externos por defecto; usar subagentes OpenClaw por misión, segmentados por scope si van en paralelo.

## Estado actual de implementación (SPEC-003)

Se ejecutaron y cerraron M0..M7 con commits en repo.

### M0 — Reproducibilidad / auditoría
- `Makefile` target `audit`
- `scripts/release_audit.py`
- `tests/test_release_audit.py`
- Commit: `8d93725`

### M1 — Retrieval Service v2 (contrato + flag)
- `scripts/retrieval_service.py`
- `state/retrieval_policy.json`
- Integración en `scripts/nl_skill_router.py`
- Tests: `tests/test_retrieval_service.py`, update router tests
- Commits: `82a7fb7`, `f6d2911`

### M2 — Hybrid retrieval E2E
- Pipeline: lexical + vector + union/dedupe + fusion + rerank + packer
- Diagnósticos por etapa en retrieval
- Test: `tests/test_retrieval_hybrid_pipeline.py`
- Commit: `168123c`

### M3 — ACL pre-topK
- ACL allow/deny aplicado antes de candidates/topK
- Tests anti-fuga:
  - `tests/test_acl_no_leak_candidates.py`
  - `tests/test_acl_no_leak_citations.py`
- Commit: `ea17b49`

### M4 — Evidence Guard universal
- `scripts/evidence_guard.py`
- Integración en router output (`evidence_guard`)
- Test: `tests/test_evidence_guard.py`
- Commit: `f91ccb0`

### M5 — Breaker global integrado con jobs
- Gating breaker en `heartbeat_worker` para `cron_jobs`, `tooling`, `retrieval`
- Estado `cooldown_skip` + jobs `skipped_cooldown`
- Test: `tests/test_breaker_blocks_jobs.py`
- Commit: `8a5c9cf`

### M6 — Day-2 ops
- `scripts/day2_doc_inventory.py`
- Inventario docs + tombstones
- Integración en heartbeat
- Tests:
  - `tests/test_day2_rename.py`
  - `tests/test_day2_delete.py`
  - `tests/test_day2_incremental_update.py`
- Commit: `c0511c7`

### M7 — Golden ampliado + gate
- Golden a 50 casos: `state/golden_set_spec002.json`
- Gate: `scripts/golden_regression_gate.py`
- Umbrales: `state/golden_regression_thresholds.json`
- Test gate: `tests/test_golden_regression_gate.py`
- Commit: `f71d295`

### Baseline pre-integración externa
- `docs/_inbox/spec003_preintegration_baseline_latest.json`
- `docs/_inbox/spec003_preintegration_baseline_latest.md`
- Commit: `0f473b0`

## Cambios de policy/owner persistidos

### Delegación
- `AGENTS.md`: default delegation ahora subagentes OpenClaw (`sessions_spawn`), no coder CLIs externos por defecto.
- `USER.md`: preferencia explícita de delegación por subagentes y segmentación por scope.
- Commit: `df691f0`

### Estilo de comunicación
- `SOUL.md` + `USER.md` ajustados con tono directo/simple para Mateo, postura clara, sin aperturas de relleno.
- Commit previo: `dd40cc8`

## Estado de calidad reciente

Suite focal de SPEC-003 ejecutada y en PASS (17 tests) justo antes del handoff.

Comando usado:
```bash
pytest -q \
  tests/test_release_audit.py \
  tests/test_retrieval_service.py \
  tests/test_retrieval_hybrid_pipeline.py \
  tests/test_acl_no_leak_candidates.py \
  tests/test_acl_no_leak_citations.py \
  tests/test_evidence_guard.py \
  tests/test_breaker_blocks_jobs.py \
  tests/test_day2_rename.py \
  tests/test_day2_delete.py \
  tests/test_day2_incremental_update.py \
  tests/test_golden_regression_runner.py \
  tests/test_golden_regression_gate.py -q
```

Golden gate actual (último run): PASS
- total: 50
- pass_rate: 0.98
- nDCG: 1.0
- MRR: 0.99
- groundedness: 1.0

## Pendiente estratégico inmediato

Mateo va a traer un diseño externo ultra experto (arquitectura superior), y pidió integración **con criterio**, no copy/paste ciego.

Reglas para integrar el diseño externo:
1. No blind merge.
2. Integración por fases con gates.
3. Mantener compatibilidad de entrypoints críticos.
4. Pruebas por fase + rollback path.

## Lo que Mateo pidió explícitamente para próxima fase

- Heartbeat “de punta”: más autónomo/proactivo con utilidad real para Mateo.
- Cambio importante de ingestión:
  - Ya NO quiere que pending se procese por heartbeat por lotes.
  - Quiere detección inmediata de `_pending` y disparo event-driven de subagente(s) hasta DONE con calidad.

Esto debe tratarse como iniciativa prioritaria en el diseño nuevo.

## Riesgo operativo actual conocido

- El repo tiene muchos cambios runtime/churn (dirty alto) por naturaleza operativa de docs/logs/state.
- El gate M0 detecta esto correctamente.
- Evitar llamar “production ready final” sin limpieza/control según política de auditoría.

## Siguiente acción sugerida al arrancar la sesión nueva

1. Leer este handoff.
2. Confirmar diseño externo del experto cuando llegue.
3. Mapear diseño externo -> plan de integración por milestones con gates duros.
4. Empezar por fase no disruptiva de adaptación (adapters + flags + tests de compatibilidad) antes de reemplazos mayores.

## Referencias rápidas

- Handoff principal: `docs/_inbox/HANDOFF_NEW_SESSION_SPEC003_2026-02-21.md`
- Baseline preintegración: `docs/_inbox/spec003_preintegration_baseline_latest.md`
- Golden gate report: `docs/_inbox/golden_regression_gate_latest.json`
- Memory del día: `memory/2026-02-21.md`
