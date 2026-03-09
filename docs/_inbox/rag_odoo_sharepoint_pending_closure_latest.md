# RAG + Odoo + SharePoint — Pending Closure (latest)

Estado: **completado**.

## Odoo (smoke no destructivo)
- Autenticación real validada (`uid=2`).
- Ejecutado smoke con workflow en modo `dry_run`:
  - `odoo_read` (partners)
  - `quote_draft` (draft idempotente)
  - `order_draft(confirm=true)` -> bloqueado por handoff gate (esperado)
- Evidencia: `docs/_inbox/odoo_smoke_latest.json`

## SharePoint local sync
- Ruta detectada y validada: `/mnt/c/Users/sgaca/SG Acabados`
- Sync incremental ejecutado con éxito:
  - `processed=2191`
  - `changed=2191`
  - `total_seen=2191`
- Evidencias:
  - `docs/_inbox/sharepoint_sync_latest.json`
  - `state/sharepoint_sync_manifest.json`

## Higiene de repo
- Se agregó `.env.odoo.local` a `.gitignore` para no versionar secreto local.
