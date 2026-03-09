# Dashboard Mateo Control v1 — Spec Congelado

Estado: APPROVED FOR BUILD
Owner: Mateo
Builder: OTTO
Fecha: 2026-02-22 (America/Lima)

## 1) Objetivo
Crear un dashboard ultra simple, visual e intuitivo para toma de decisiones rápida de Mateo.

Regla de diseño v1:
- Leer en 15 segundos.
- Ver qué pasa, qué importa y qué hacer ahora.
- Cero ruido técnico.

## 2) Alcance v1 (cerrado)

### Topbar fija
1. Estado OTTO
   - Disponible (verde)
   - Ocupado (amarillo)
   - Bloqueado (rojo)
2. Delegación en vivo
   - Total activas
   - Chips: Subagente / Coder
3. Botones rápidos
   - Actualizar
   - Ver actividad
   - Pausar delegación

### Tabs
- SG
- Personal

### SG (4 tarjetas)
1. Caja/Cobranza hoy
2. Pipeline activo
3. Operación en riesgo
4. Siguiente mejor decisión (1 sola)

### Personal (4 tarjetas)
1. Top 3 del día
2. Pendientes críticos
3. Próxima decisión importante
4. Siguiente mejor acción

### Panel lateral (actividad)
- Últimos 5 eventos
- Estado por evento
- Chip si es Subagente/Coder

## 3) Fuera de alcance v1
- Gráficos complejos
- Módulos avanzados financieros
- Simulaciones predictivas
- Automatizaciones agresivas
- Multiusuario

## 4) Contrato de datos v1

## Topbar
- otto_status: available|busy|blocked
- active_delegations_total: number
- active_subagents: number
- active_coders: number

## SG cards
- sg_cash_receivable_7d: number
- sg_overdue_count: number
- sg_hot_pipeline_value: number
- sg_hot_opportunities_count: number
- sg_ops_risk_count: number
- sg_top_risk_label: string
- sg_next_best_decision: string
- sg_next_best_decision_impact: high|medium|low

## Personal cards
- personal_top3: string[] (max 3)
- personal_critical_count: number
- personal_due_today_count: number
- personal_next_decision: string
- personal_next_action: string
- personal_next_action_impact: high|medium|low

## Activity panel
- events: array(max 5)
  - time
  - label
  - status: running|done|blocked
  - type: subagent|coder|system|task

## 5) UX rules (no-negotiables)
- Semáforo visible en cada tarjeta.
- Una recomendación principal por tab.
- Botones grandes y claros.
- Sin jerga técnica.
- Si un bloque no cambia decisión => se elimina.

## 6) Arquitectura de implementación
- Frontend: web responsive mobile-first
- Backend/API: endpoints simples para topbar, SG, Personal y activity
- Auth: acceso privado inicial (single owner)
- Deploy: Vercel (prod) + GitHub repo

## 7) Plan de construcción (ejecución)
1. Scaffold app + rutas base
2. UI v1 completa (estática)
3. API mock + contratos tipados
4. Integración runtime OTTO (status/delegations)
5. Integración SG mínima viable
6. Integración Personal mínima viable
7. Deploy Vercel + smoke test móvil

## 8) Criterios de éxito v1
- Mateo entiende estado y prioridad en <= 15 segundos.
- Puede tomar 1 decisión y ejecutarla en <= 2 clicks.
- Vista usable en móvil y laptop.
- Datos no disponibles no rompen UX (fallback explícito).

## 9) Próximo paso inmediato
Construir scaffold del proyecto dashboard y dejar primer deploy preview en Vercel.
