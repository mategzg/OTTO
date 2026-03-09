# LEARNINGS

## [LRN-20260223-001] correction

**Logged**: 2026-02-23T01:40:00-05:00
**Priority**: high
**Status**: promoted
**Area**: docs

### Summary
Repo-specific capability questions were answered from memory search only, missing existing repo evidence.

### Details
`memory_search` did not return plugin integration artifacts because they live under `docs/_inbox` and `state/*`. User corrected with explicit commits and files. Correct approach is dual-check: policy memory_search + repo artifact verification before conclusion.

### Suggested Action
Always run repo verification protocol for specific repo claims: check commits + artifact files before stating availability/integration status.

### Metadata
- Source: user_feedback
- Related Files: AGENTS.md, USER.md
- Tags: repo-verification, memory-gap, reliability
- Pattern-Key: verify.repo_claims.before_answer
- Recurrence-Count: 1
- First-Seen: 2026-02-23
- Last-Seen: 2026-02-23

### Resolution
- **Resolved**: 2026-02-23T01:40:00-05:00
- **Commit/PR**: pending
- **Notes**: Protocol promoted to AGENTS.md and USER.md.

---

## [LRN-20260223-002] correction

**Logged**: 2026-02-23T08:10:00-05:00
**Priority**: critical
**Status**: pending
**Area**: docs

### Summary
No debo reportar “integrado/operativo” cuando solo existe inventario en docs/state sin consumo real en runtime.

### Details
Se verificó que `docs/_inbox/plugin_drop/*` y registros `state/plugin_*` y `state/cc_plugin_*` existen, pero su uso está acotado a scripts de ingest/certificación y no aparece integración activa en el runtime principal. Esto confirma riesgo de “humo” si comunico estado sin distinguir `catalogado` vs `operativo`.

### Suggested Action
Introducir estatus binario verificable por capa: `CATALOGADO`, `RUTEADO`, `EJECUTABLE`, `OPERATIVO_EN_PROD`, y exigir evidencia de consumo runtime antes de afirmar operación.

### Metadata
- Source: user_feedback
- Related Files: state/plugin_runtime_registry.json, state/cc_plugin_runtime_registry.json, scripts/plugin_drop_processor.py, scripts/cc_plugin_ingest.py
- Tags: truthfulness, integration, runtime-evidence
- Pattern-Key: never.claim.operational.without.runtime_path
- Recurrence-Count: 2
- First-Seen: 2026-02-23
- Last-Seen: 2026-02-23

### Resolution
- **Resolved**: 2026-02-23T15:55:00-05:00
- **Commit/PR**: pending
- **Notes**: Reforzar respuesta con distinción explícita Skills vs Plugins y verificación directa en `state/cc_plugin_runtime_registry.json` + reportes `_latest`.

---
