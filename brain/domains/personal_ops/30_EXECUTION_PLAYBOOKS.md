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

## Criterio de cierre
Sin evidencia verificable de gate final, el playbook sigue abierto.