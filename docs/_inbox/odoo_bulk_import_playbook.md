# Odoo Bulk Import Playbook (Alta Confiabilidad)

## Objetivo
Pipeline para importar contactos masivos con:
- validación por fila,
- deduplicación por email/teléfono,
- modo seguro `dry-run` / `apply`,
- artefacto de rollback lógico.

## Archivos
- Script: `scripts/odoo/odoo_bulk_import.py`
- Template: `templates/odoo_import_contacts_template.csv`
- Tests: `tests/test_odoo_bulk_import.py`

## Formato esperado de entrada
CSV (recomendado) o XLSX con columnas:
- `name` (obligatorio)
- `email` (opcional, validado)
- `phone` (opcional)
- `mobile` (opcional)
- `company_name`, `street`, `city`, `state`, `zip`, `country` (opcionales)

Regla mínima de contacto: al menos uno entre `email`, `phone` o `mobile`.

## Ejecución
### 1) Simulación segura (dry-run)
```bash
python scripts/odoo/odoo_bulk_import.py \
  --input data/contacts_batch.csv \
  --mode dry-run \
  --report-dir reports/odoo
```

### 2) Aplicación real (requiere doble confirmación)
```bash
python scripts/odoo/odoo_bulk_import.py \
  --input data/contacts_batch.csv \
  --mode apply \
  --explicit-apply \
  --report-dir reports/odoo
```

> Sin `--explicit-apply`, el script bloquea la importación real.

## Reportes generados
- `bulk_import_report_<timestamp>.json`
  - resumen total
  - errores por fila (`validation`, `duplicates`, `existing`)
  - ids creados en apply
- `bulk_import_rollback_<timestamp>.json` (solo cuando hay creación)
  - `created_ids`
  - estrategia de rollback lógico: desactivar (`active=False`)

## Recomendaciones operativas para lotes gigantes
1. Pre-normalizar Excel→CSV (UTF-8) y limpiar caracteres extraños.
2. Dividir en chunks grandes pero controlados (ej. 10k-50k filas).
3. Ejecutar siempre `dry-run` primero.
4. Revisar top errores y corregir origen.
5. Re-ejecutar hasta error rate aceptable.
6. Solo luego correr `apply --explicit-apply`.

## Integración Odoo real
`OdooClient` viene como interfaz. Debe conectarse a RPC de Odoo para:
- `find_existing_contacts(emails, phones)`
- `create_contacts(records)`
- `deactivate_contacts(contact_ids)` (rollback lógico)

Esto permite mantener testabilidad y control por entorno (dev/stage/prod).
