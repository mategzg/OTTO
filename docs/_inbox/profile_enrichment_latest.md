# Reingest Profile Enrichment — latest

Fecha (UTC): 2026-02-22T19:05:00Z
Fuente: `20260222T162442Z_065f800160 (reingest v2 artifacts)`

## Archivos tocados
- `memory/01_PROFILE_CURRENT.md`
- `memory/03_PREFERENCES.ndjson`
- `memory/05_DECISIONS.ndjson`
- `memory/06_TIMELINE.ndjson`
- `memory/profile/00_INDEX.md`
- `memory/profile/40_SYSTEM_PREFERENCES.md`
- `memory/profile/50_DECISION_PATTERNS.md`
- `memory/profile/95_REINGEST_PROFILE_EVIDENCE_20260222.md`
- `brain/domains/personal_ops/00_INDEX.md`
- `brain/domains/personal_ops/95_CAPABILITY_EXTRACT_20260222.md`
- `brain/personal/2026-02-22_reingest_profile_insights.md`

## Métricas
- preferences_records: **7**
- decisions_records: **4**
- timeline_records: **5**
- profile_queries: **20**
- profile_hit_rate: **0.95**
- brain_queries: **20**
- brain_hit_rate: **1.0**

## Cobertura
- Fuertes:
  - identity_mission
  - interaction_contract
  - execution_preferences
  - safety_boundaries
  - operational_history_markers
- Gaps:
  - biographical_non_technical_profile
  - stable_non_work_personal_preferences

## QA separado
- Profile queries: 20 | hit-rate: 0.95
- Brain queries: 20 | hit-rate: 1.0

### Defectos profile<->brain
- No se detectaron confusiones activas en esta pasada.

## Próximos pasos
- Mantener dedupe por key antes de futuras promociones de perfil.
- Agregar test de frontera PROFILE vs BRAIN en pipeline de ingest.
- Revisar periódicamente decisiones tácticas para desactivarlas o archivarlas cuando caduquen.
