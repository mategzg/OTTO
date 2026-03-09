# RAG + Odoo + SharePoint Upgrade (latest)

## Resumen
Estado: **partial_complete** con pipeline operativo implementado y validado por tests locales.

## Odoo E2E
- Implementado `scripts/odoo/odoo_workflow.py` con:
  - `odoo_read`
  - `odoo_write`
  - `quote_draft`
  - `order_draft`
- Guardrails incluidos:
  - idempotency keys (`state/odoo/idempotency_store.json`)
  - audit log (`logs/odoo_workflow_audit.jsonl`)
  - handoff gate para confirmación final de orden (`order_draft(confirm=True)` bloquea por humano).
- Cobertura QA: `tests/test_spec004_m5_odoo_workflow.py`.

## SharePoint local ingest E2E
- Ruta detectada/validada en host: `/mnt/c/Users/sgaca/SG Acabados`.
- Implementado `scripts/sharepoint_sync.py`:
  - detección de root SharePoint local
  - scan incremental por `mtime + hash`
  - manifest incremental (`state/sharepoint_sync_manifest.json`)
  - dedupe por hash
  - conversión markdown usable para `md/txt/html` + fallback seguro para `docx/pdf/xlsx`
  - clasificación `audience_tag/domain_tag` + `route_target` (SG vs personal ops)
- Cobertura QA: `tests/test_spec004_m4_sharepoint_sync.py`.

## RAG optimization
- Añadido gate reproducible por categoría/autor:
  - `scripts/retrieval_regression_gate.py`
  - dataset/thresholds en `state/retrieval_regression_set.json`
  - reporte en `docs/_inbox/retrieval_regression_gate_latest.json`
- Cobertura QA: `tests/test_retrieval_regression_gate.py`.

## QA ejecutado
- `19 passed` en suite focal:
  - spec004 odoo workflow
  - spec004 sharepoint sync
  - retrieval regression gate
  - retrieval hybrid pipeline
  - whatsapp boundary no-leak
  - odoo client/actions

## Pendientes
- Smoke real no destructivo contra Odoo admin (draft/no-op) en runtime real.
- Conversión semántica profunda docx/pdf/xlsx (actual: fallback seguro).
- Commit final bloqueado por repo ya sucio de origen + `.env.odoo.local` no trackeado.

## Archivos tocados
- `scripts/odoo/odoo_workflow.py`
- `scripts/sharepoint_sync.py`
- `scripts/retrieval_regression_gate.py`
- `tests/test_spec004_m5_odoo_workflow.py`
- `tests/test_spec004_m4_sharepoint_sync.py`
- `tests/test_retrieval_regression_gate.py`
