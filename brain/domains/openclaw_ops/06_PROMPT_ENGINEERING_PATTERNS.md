# Prompt Engineering Patterns (Derived)

## Purpose

Capturar patrones derivados del material de inverse engineering de Claude para mejorar nodos, cards y protocolos de operacion.

## Use when

- Diseñas nodos de dominio con rutas de decision.
- Quieres convertir prompts largos en protocolos accionables de bajo costo.

## Avoid when

- El objetivo sea copiar material crudo literal.
- Se requiera indexar documentos fuente sin derivacion.

## Routing

- Para estructura de prompts operativos: usar plantillas en `brain/templates/OPS_NODE_TEMPLATE.md` y `brain/templates/OPS_CARD_TEMPLATE.md`.
- Para decisiones de seccionado: seguir regla "When to use / Avoid when / Routing / Maintenance / Links".
- Para prompts multi-herramienta: separar en `Objective`, `Scope`, `Gates`, `Stop conditions`, `Evidence`.

## Derived Patterns

- Patrón 1: especificar autoridad y orden de lectura antes de ejecutar.
- Patrón 2: separar acciones permitidas vs prohibidas para evitar drift.
- Patrón 3: incluir criterios de bloqueo (`STOP CONDITIONS`) antes de cambios con riesgo.
- Patrón 4: exigir cierre determinista (ledger + report + evidence paths).
- Patrón 5: definir rutas de respuesta tipo "si preguntas X, vas a Y" para minimizar contexto.

## Maintenance

- Fuente cruda preservada en `vault/inbox_raw/claude_inverse_engineering/`.
- Actualizar derivados cuando cambie el corpus o aparezcan nuevos patrones utiles.

## Links

- `brain/04_WRITING_STYLE.md`
- `brain/templates/OPS_NODE_TEMPLATE.md`
- `brain/templates/OPS_CARD_TEMPLATE.md`
