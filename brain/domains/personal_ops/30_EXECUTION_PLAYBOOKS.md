# 30 — Execution Playbooks

## P1. Incidente operativo
1. Capturar evidencia mínima (síntoma + rutas + timestamps).
2. Formular hipótesis de causa raíz.
3. Aplicar fix mínimo suficiente + barrera preventiva.
4. Ejecutar test/gate de regresión.
5. Confirmar estado post-fix y reportar evidencia.

## P2. Ingest/backlog
1. Normalize -> 2) Triage -> 3) Plan -> 4) Apply/write -> 5) Move processed.
6. Verificar cierre: `pending=0` o listar remanentes justificados.

## P3. Presión de costo/contexto
1. Reducir salida a esencial accionable.
2. Priorizar decisiones irreversibles/urgentes.
3. Postergar detalle no crítico a anexo o subagente.
4. Checkpoint con estado + siguiente paso claro.

## P4. Cola/estado sucio
1. Backup puntual.
2. Cleanup controlado y reversible.
3. Re-scan/rebuild índice.
4. Validar integridad (sin pérdida no intencional).

## P5. Single-Writer para cambios de repo
1. Definir escritor principal (owner agent) y bloquear colisiones de edición.
2. Permitir paralelismo solo en análisis/research/scouting con scopes no superpuestos.
3. Consolidar cambios finales en una sola pasada de escritura.
4. Ejecutar test/gates al final de la integración única.

## P6. Guardrail no-destructivo por defecto
1. Evitar stash masivo, vaciado o move-all como primera opción.
2. Elegir cambios incrementales y reversibles por lotes pequeños.
3. Si una acción destructiva es inevitable, exigir backup + plan de rollback explícito.
4. Registrar evidencia del antes/después.

## Criterio de cierre
Sin evidencia verificable de gate final, el playbook sigue abierto.