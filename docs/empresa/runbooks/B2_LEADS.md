# Runbook B2 - Leads (On-demand)

B2 se ejecuta solo bajo demanda (Telegram/WhatsApp/manual). No cron automatico.

## PLAN FIRST (obligatorio)

1. Crear plan en `plans/` (ej: `plans/2026-02-11-b2.md`).
2. Definir sector, filtro geografico y salida.
3. Recién ejecutar prospeccion.

## Outputs esperados

- Documento principal:
  - `docs/empresa/leads/leads_YYYY-MM-DD.md`
- Datos tabulares (si aplica):
  - CSV/Excel en `docs/empresa/leads/`

## Cierre de mision

1. Agregar filas relevantes a `docs/empresa/ledger.md` via `scripts/append_ledger.py`.
2. Ejecutar `python index_docs.py`.
3. Actualizar status/kanban/log.
