# 90 Legacy Recovery

Lectura minima:

1. `scripts/capability_inventory.py`
2. `scripts/legacy_coldstore_audit.py`
3. `scripts/legacy_gap_detector.py`
4. `scripts/legacy_capability_inventory.py`
5. `scripts/legacy_recovery_worker.py`

Objetivo:

- Auditar `vault/_salvage/**` y `vault/_quarantine/**` sin restaurar destructivamente.
- Detectar capacidades potenciales faltantes vs repositorio actual.
- Preparar recuperacion por lotes solo para documentacion segura (no codigo).

Reglas:

- `state/legacy_recovery_policy.json` manda; `enabled=false` por defecto.
- Legacy Gap v2 suprime ruido de path y artefactos de ejecucion (`docs/_inbox/**`, `logs/**`, `ops/**`, `copilots/**`).
- `scripts/legacy_capability_inventory.py` tipa candidatos (`script/hook/policy_state/brain_node/skill/doc_value`) y marca `GAP/NO VERIFICADO` cuando no hay equivalencia clara.
- Recovery worker v2 solo empaqueta tipos permitidos por policy (`doc_value`,`brain_node` por default) y nunca auto-mergea codigo.
- Packaging en `vault/inbox_raw/_pending_drop/legacy_recovery/` con `MANIFEST.json` + `EVENT_META.json` (`source_kind=legacy_recovery_v2`).
