# Card: Odoo Operations — Toolkit Completo SG

> Fuente: odoo_toolkit_usage.md, odoo_ops_assistant_workflows.md, odoo_sales_inventory_purchase_playbook.md, odoo_sip_automation_matrix.md, odoo_hr_project_helpdesk_capability_report.md, odoo_minimum_permissions_checklist_by_role.md, odoo_bulk_import_playbook.md (legacy)
> Dominio: sg_acabados / odoo

## Toolkit Disponible
- `scripts/odoo/odoo_client.py` — Cliente RPC con auth, retries, timeout, auditoría
- `scripts/odoo/odoo_actions.py` — Acciones atómicas: contacto, lead, actividad, oportunidades
- `scripts/odoo/odoo_cli.py` — CLI interno (ping-auth, create-contact, create-lead, schedule-activity)
- `scripts/odoo/odoo_bulk_import.py` — Import masivo CSV/XLSX

## Variables de Entorno Necesarias
`ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD` (+ opcional: TIMEOUT, RETRIES, RETRY_BACKOFF)

## Principios Operativos
1. **Read-first:** consultar contexto antes de cambios
2. **Least privilege:** permisos mínimos por rol
3. **Confirmación contextual:** acciones ámbar requieren OK humano
4. **Auditabilidad:** request, actor, resultado, diff
5. **Privacidad:** enmascarar PII

## Matriz de Riesgo SIP (Sales/Inventory/Purchase)

| Acción | Riesgo | Auto permitido | Requiere OK humano |
|--------|--------|----------------|-------------------|
| Crear cotización | Medio | Sí (dry-run) | No* |
| Confirmar SO | Alto | No | Sí |
| Reservar stock | Medio | Sí | No |
| Validar entrega | Alto | No (si divergencia) | Sí |
| Crear factura borrador | Medio | Sí | No |
| Publicar factura | Alto | No | Sí |
| Crear RFQ | Medio | Sí | No |
| Confirmar PO | Alto | No | Sí |

## Bloqueos Duros
- Monto ≥ threshold crítico → bloquear
- Cliente/proveedor en lista de riesgo → bloquear
- Campos fiscales faltantes → bloquear
- Dedupe positivo con alta similitud → bloquear

## Roles OTTO en Odoo
1. **Reader:** solo lectura, sin PII sensible
2. **Operator Project:** read/create/write tasks, sin unlink
3. **Operator Helpdesk:** read/create/write tickets, sin export PII
4. **HR Limited:** lectura restringida, sin nómina/salud/disciplina

## Estado Actual
- **Sin conexión Odoo activa** — falta configurar variables de entorno
- Scripts listos para conectar cuando se provea acceso
