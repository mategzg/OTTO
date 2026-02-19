# Legacy Recovery

## Purpose

Operar el ciclo seguro de auditoria y recuperacion de conocimiento legacy desde `vault/_salvage` y `vault/_quarantine`.

## Use when

- Existe duda de capacidades/features perdidas en coldstore.
- Necesitas comparar coldstore contra el sistema actual sin restaurar codigo automaticamente.
- Quieres habilitar recuperacion por lotes de documentacion segura hacia `_pending_drop`.

## Avoid when

- Se busca auto-merge de codigo legacy (prohibido por policy).
- El material contiene secretos o archivos reservados de instruction surface.

## Routing

1. Inventario actual: `python3 scripts/capability_inventory.py --root . --scan`
2. Auditoria coldstore: `python3 scripts/legacy_coldstore_audit.py --root . --scan`
3. Deteccion de faltantes: `python3 scripts/legacy_gap_detector.py --root . --scan`
4. Recovery por lotes (solo docs, opt-in): `python3 scripts/legacy_recovery_worker.py --once --root .`
5. Referencia canon de flujo: `repo_map/90_LEGACY_RECOVERY.md`

## Maintenance

- Mantener `state/legacy_recovery_policy.json` con `enabled=false` por defecto.
- Revisar que `scripts/brain_index_build.py` y `state/workspace_hygiene_policy.json` sigan excluyendo coldstore/inbox raw.

## Links

- `repo_map/90_LEGACY_RECOVERY.md`
- `state/legacy_recovery_policy.json`
- `docs/_inbox/legacy_coldstore_audit_latest.json`
- `docs/_inbox/legacy_gap_report_latest.json`
