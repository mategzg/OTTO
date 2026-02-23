# Odoo SG — Smoke test en apps (ejecución real)

Fecha: 2026-02-22 America/Lima
Instancia: `https://sg-acabados1.odoo.com` · DB: `sg-acabados1`

## Resultado general
- ✅ Se ejecutó caso de prueba real en el stack completo de apps.
- ✅ Se validó creación/lectura en la mayoría de módulos críticos.
- ⚠️ Quedaron algunos módulos en validación parcial (solo lectura o conteo), normal para primera pasada de smoke.

## Casos creados (escritura real)
- Contacto (`res.partner`): **ID 55**
- Lead CRM (`crm.lead`): **ID 16**
- Conversación/chatter (`mail.message`): **ID 1954**
- Actividad pendiente (`mail.activity`): **ID 4**
- Evento calendario (`calendar.event`): **ID 1**
- Cotización venta (`sale.order`): **ID 4**
- Tarea proyecto/tablero (`project.task`): **IDs 2, 3**
- Factura borrador (`account.move`): **ID 7**
- Orden de compra (`purchase.order`): **ID 5**
- Candidato reclutamiento (`hr.applicant`): **ID 4**

## Casos de validación por lectura/conteo
- Citas (`appointment.type`): OK
- Documentos (`documents.document`): OK
- Planeación (`planning.slot`): OK
- Marketing (`mailing.mailing`): OK
- Inventario (`stock.picking`): OK
- Empleados (`hr.employee`): OK
- Asistencias (`hr.attendance`): OK
- Gastos (`hr.expense`): OK
- Ajustes (`res.config.settings` modelo presente): OK

## Evidencia bruta
- `docs/_inbox/odoo_all_apps_smoke_20260222-205841.json`
- `docs/_inbox/odoo_all_apps_smoke_fix_20260222-205919.json`

## Próximo paso operativo
- Pasar de smoke a **catálogo de acciones productivas NL→Odoo** por fase:
  1) CRM+Ventas
  2) Compras+Inventario
  3) Contabilidad+Gastos
