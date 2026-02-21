# Personal Ops Domain (OTTO)

Dominio de inteligencia operativa de ejecución.
Incluye **cómo decidir, ejecutar, delegar y mejorar**; excluye perfil/visión personal.

## Ramas
- `10_DECISION_HEURISTICS.md` — reglas de decisión rápida y segura.
- `20_FAILURE_PATTERNS.md` — fallos recurrentes + detección temprana.
- `30_EXECUTION_PLAYBOOKS.md` — secuencias ejecutables por tipo de trabajo.
- `40_CHANNEL_OPERATING_RULES.md` — operación por canal y señal esperada.
- `50_RESOURCE_BUDGET_TACTICS.md` — control de costo/contexto sin sobre-monitoreo.
- `60_DELEGATION_DOCTRINE.md` — cuándo y cómo delegar con cierre verificable.
- `70_BRAIN_FIRST_PROTOCOL.md` — composición de ramas expertas antes de actuar.
- `80_SELF_OPTIMIZATION_PROTOCOL.md` — ciclo de mejora continua anclado en artefactos.
- `90_REVIEW_QUEUE.md` — cola de consolidación y limpieza de reglas.

## Mini-matriz de composición (task-type -> ramas obligatorias)
- Incidente operativo -> `10` + `20` + `30` (+ `50` si hay presión de costo).
- Tarea larga/compleja -> `10` + `60` + `70` (+ `30` para flujo E2E).
- Respuesta multi-dominio -> `70` + ramas del dominio técnico aplicable + `10`.
- Optimización de costo/tokens -> `50` + `30` + `40`.
- Mejora estructural post-ejecución -> `80` + `20` + `90`.
- Operación por canal (Telegram/WhatsApp/Discord) -> `40` + `10` (+ `50` si hay budget guard).

## Regla de uso
Antes de ejecutar: identificar task-type, cargar matriz, componer ramas, actuar con evidencia.
Si falta certeza operativa: `GAP/NO_VERIFICADO` + plan de verificación.