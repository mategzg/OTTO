# 50 — Resource Budget Tactics

## Modo adaptativo
- **Verde**: operación normal optimizada.
- **Amarillo**: compresión de contexto + prioridad alta.
- **Rojo**: solo esencial + checkpoints frecuentes.

## Reglas (MUST)
- Medir por **cambio de peso de tarea**, no por polling constante.
- El monitoreo nunca debe costar más que el ahorro esperado.
- Aplicar guardias de retención/liberación solo donde el costo lo justifique.
- Offload de trabajo largo con delegación (`60`) y supervisión mínima efectiva.

## Señales de cambio de modo
- Aumento brusco de tokens/contexto por turno.
- Multiplicación de ramas activas en una sola respuesta.
- Latencia/retrabajo en subida.

## Salida operativa
Siempre reportar: modo actual, recorte aplicado y riesgo residual.