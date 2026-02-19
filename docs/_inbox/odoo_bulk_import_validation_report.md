# Validation Report — Odoo Bulk Import Pipeline

Fecha: 2026-02-16

## Alcance validado
Se verificó que el pipeline cumple los requisitos del track:

1. **Modos `dry-run` / `apply`** ✅
2. **Dedupe por teléfono/email** ✅
3. **Reporte de errores por fila** ✅
4. **Bloqueo de import real sin `--explicit-apply`** ✅
5. **Rollback lógico (artefacto con IDs creados)** ✅

## Evidencias (tests)
Archivo: `tests/test_odoo_bulk_import.py`

- `test_validation_and_dedupe`
  - valida reglas de fila y detecta duplicados en input.
- `test_apply_requires_explicit_flag`
  - comprueba guardrail de seguridad para apply.
- `test_dry_run_does_not_create`
  - asegura cero creación en dry-run.
- `test_apply_creates_and_writes_rollback`
  - confirma creación y archivo de rollback lógico.

## Riesgos/pendientes conocidos
- La conexión real a Odoo está abstraída en `OdooClient` y requiere implementación RPC del entorno productivo.
- Para `.xlsx` se necesita dependencia `openpyxl`.

## Conclusión
La base de alta confiabilidad queda implementada para operación segura en lotes grandes, con controles de seguridad y trazabilidad suficientes para pasar a integración con Odoo real.
