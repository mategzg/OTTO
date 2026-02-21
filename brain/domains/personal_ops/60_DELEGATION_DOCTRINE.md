# 60 — Delegation Doctrine

## Cuándo delegar (MUST)
- Tareas largas, multi-etapa o que bloquean disponibilidad del agente principal.
- Investigación extensa o refactors con múltiples archivos/gates.

## Contrato mínimo de delegación
- Scope estricto (incluye/excluye rutas).
- Gates de calidad/verificación.
- Formato de salida esperado.
- `HANDOFF_FILE` obligatorio con evidencia y pendientes.

## Flujo E2E
Emitir misión -> ejecutar -> recibir handoff -> verificar gates -> responder con evidencia.

## Diagnóstico rápido de fallos
1. Pairing/auth/permisos.
2. Prompt contract incompleto.
3. Lock/estado colgado.
4. Fallback plan (reemitir o ejecutar local).

## Regla de cierre
Sin handoff válido + verificación, no hay DONE.