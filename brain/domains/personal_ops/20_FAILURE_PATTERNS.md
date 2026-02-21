# 20 — Failure Patterns

## Patrones recurrentes + señal temprana + contención
- **Lock fantasma de delegación**
  - Señal: estado “activo” sin nuevos artefactos/handoff.
  - Contención: cortar lock, reemitir misión con gates explícitos, exigir HANDOFF_FILE.
- **Ingest atascado por granularidad incorrecta**
  - Señal: progreso parcial repetido, pendientes no bajan.
  - Contención: mover en source-root correcto, reindexar, validar `pending=0`.
- **Browser relay “reachable” pero no operativo**
  - Señal: puerto responde pero no hay tab attach/token válido.
  - Contención: validar attach real + token/sesión antes de acciones UI.
- **Monitoreo más caro que el ahorro**
  - Señal: muchas verificaciones con bajo impacto operativo.
  - Contención: bajar frecuencia, medir por cambio de estado, no por polling fijo.

## Regla
Cada incidente nuevo debe convertirse en heurística (`10`), playbook (`30`) o cola de revisión (`90`).