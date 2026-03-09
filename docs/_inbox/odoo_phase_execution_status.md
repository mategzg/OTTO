# Odoo SG — Estado de ejecución por fases

Fecha: 2026-02-22 (America/Lima)

## Contexto operativo confirmado
- Instancia: `https://sg-acabados1.odoo.com`
- DB: `sg-acabados1`
- Usuario operativo: admin del owner
- Company ID: `1`
- Versión observada: Odoo 19 (trazas XML-RPC)

## Pre-flight ejecutado
- ✅ Autenticación exitosa por API (uid=2)
- ✅ Descubiertas apps instaladas relevantes: CRM, Ventas, Compras, Inventario, Contabilidad, Proyecto, Documentos, RRHH, Asistencias, Reclutamiento, Gastos, Calendar, Appointments, Discuss.
- ⚠️ Observación técnica: para Odoo 19 conviene migrar operaciones a JSON-2 como capa principal; XML-RPC sigue operativo pero legacy.

## Fase 1 — CRM + Ventas
Estado: **EN CURSO**

Objetivo de ejecución:
1. Contactos (`res.partner`) — alta/actualización deduplicada por email/teléfono.
2. Leads (`crm.lead`) — alta, stage update, actividades.
3. Cotizaciones (`sale.order`) — creación con líneas, confirmación controlada.

Entregables operativos de fase:
- Catálogo NL→acción para CRM/Ventas.
- Acciones seguras con idempotencia por `external_ref`.
- Registro auditable por operación (request_id, modelo, método, ids).

## Fase 2 — Compras + Inventario
Estado: PENDIENTE

Objetivo:
- `purchase.order` end-to-end
- recepciones/movimientos (`stock.picking`, `stock.move`)
- control básico de disponibilidades

## Fase 3 — Contabilidad + Gastos
Estado: PENDIENTE

Objetivo:
- facturación cliente/proveedor (`account.move`)
- pagos (`account.payment`)
- gastos (`hr.expense`)
- conciliación y trazabilidad de cierre

## Próxima acción inmediata
- Implementar/activar runner de operaciones de Fase 1 con comandos transaccionales listos para ejecución desde chat.
