# Runbook B1 - Licitaciones (On-demand)

B1 se ejecuta solo bajo demanda (Telegram/WhatsApp/manual). No cron automatico.

## PLAN FIRST (obligatorio)

1. Crear plan en `plans/` (ej: `plans/2026-02-11-b1.md`).
2. Definir alcance, fuentes, criterios de filtrado y salida.
3. Recién ejecutar busqueda/analisis.

## Outputs esperados

- Documento principal:
  - `docs/empresa/licitaciones/licitaciones_YYYY-MM-DD.md`
- Descargas ordenadas (si aplica):
  - `docs/empresa/licitaciones/downloads/`

## Cierre de mision

1. Agregar filas relevantes a `docs/empresa/ledger.md` via `scripts/append_ledger.py`.
2. Ejecutar `python index_docs.py`.
3. Actualizar status/kanban/log.
