# Dashboard OTTO v1 — Spec congelado

## Objetivo
Dashboard ejecutivo ultra visual para decidir en <15 segundos y accionar sin fricción desde celular/laptop.

## Estructura general (no negociable)
- Topbar fija
- 2 tabs: `SG` | `Personal`
- Grid de tarjetas grandes (2x2 desktop, 1 columna mobile)
- Semáforos + iconos + números grandes
- Cero tablas técnicas

## Topbar
### Izquierda: Estado OTTO
- Píldora única:
  - 🟢 Disponible
  - 🟡 Ocupado
  - 🔴 Bloqueado

### Centro: Delegación en vivo
- Total activo (ej: `3 activas`)
- Chips: `Subagente xN`, `Coder xN`
- Lista corta de delegaciones con mini barra de progreso

### Derecha: Acciones rápidas
- `Actualizar`
- `Ver actividad` (abre panel lateral)
- `Pausar delegación` (requiere confirmación)

## Tab SG (2x2)
### Tarjeta 1 — Caja y Cobranza Hoy
- Principal: `S/ XX,XXX por cobrar (7 días)`
- Subdato: `X vencidas`
- Semáforo
- CTA: `Ver críticas`

### Tarjeta 2 — Pipeline Activo
- Principal: `S/ XXX,XXX en pipeline caliente`
- Subdato: `X oportunidades esta semana`
- Semáforo
- CTA: `Ver oportunidades`

### Tarjeta 3 — Operación en Riesgo
- Principal: `X frentes en ámbar/rojo`
- Subdato: `Top riesgo: [nombre corto]`
- Semáforo
- CTA: `Ver bloqueos`

### Tarjeta 4 — Siguiente Mejor Decisión
- Recomendación única y clara
- Impacto: Alto/Medio/Bajo
- CTA principal: `Ejecutar con OTTO`
- CTA secundaria: `Ver alternativa`

## Tab Personal (2x2)
### Tarjeta 1 — Top 3 del Día
- Máximo 3 bullets
- Checkbox visual simple

### Tarjeta 2 — Pendientes Críticos
- Principal: `X críticos`
- Subdato: `Y vencen hoy`
- CTA: `Ordenar ahora`

### Tarjeta 3 — Próxima Decisión Importante
- Una sola decisión destacada
- Fecha/hora sugerida
- CTA: `Resolver ahora`

### Tarjeta 4 — Siguiente Mejor Acción
- Recomendación única de OTTO
- Impacto estimado
- CTA: `Hazlo por mí`

## Panel lateral — Actividad
- Últimos 5 eventos
- Formato: `Hora · Acción`
- Estado: en curso / completado / bloqueado
- Chip origen si aplica: Subagente / Coder

## Reglas de diseño
1. Todo se entiende en 15 segundos.
2. Máximo 1 recomendación principal por tab.
3. Semáforos siempre visibles.
4. Si no cambia decisiones, se elimina.
5. Cero jerga técnica.

## Criterios de aceptación v1
- Mobile-first usable en una mano
- Topbar y tabs funcionando
- 8 tarjetas con CTA y semáforo
- Actividad lateral funcional
- Fallback de datos sin romper UI
- Acciones críticas con confirmación
