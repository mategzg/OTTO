# Card: Odoo Bulk Import Pipeline

> Fuente: scripts/odoo/odoo_bulk_import.py (legacy, recuperado feb-2026)
> Ubicación actual: `scripts/odoo/odoo_bulk_import.py` + `tests/test_odoo_bulk_import.py`

## Qué hace
Pipeline de importación masiva de contactos a Odoo (ERP de SG Acabados).

## Capacidades
- **Input:** CSV o XLSX (openpyxl requerido para XLSX)
- **Validación:** nombre obligatorio, email formato válido, al menos un contacto (email/phone/mobile)
- **Deduplicación:** dentro del archivo + contra Odoo remoto (si habilitado)
- **Modos:** `dry-run` (default) | `apply` (requiere `--explicit-apply` como safety flag)
- **Rollback:** genera JSON con IDs creados para rollback lógico (deactivate)
- **Campos:** name, email, phone, mobile, company_name, street, city, state, zip, country

## Estado
- OdooClient tiene placeholder (`raise NotImplementedError`) — necesita conectarse a XML-RPC/JSON-RPC real
- Script funcional para validación y dry-run sin conexión Odoo

## Uso
```bash
python scripts/odoo/odoo_bulk_import.py --input contacts.csv --mode dry-run
python scripts/odoo/odoo_bulk_import.py --input contacts.csv --mode apply --explicit-apply
```

## Patrón de diseño
Safety-first: no aplica sin flag explícito, siempre genera reporte, siempre genera rollback.
