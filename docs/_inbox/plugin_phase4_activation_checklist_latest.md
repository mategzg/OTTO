# Plugin Activation Checklist (Fase 4)

Actualizado: 2026-02-23T13:16:00-05:00

## Verdad operativa
No puedo completar autenticación de conectores externos sin credenciales/sesiones del owner.
Lo que sí quedó listo: matriz priorizada + criterio de certificación PASS/FAIL.

## Lote 1 (ejecutar primero)
1. **sales**
2. **customer-support**
3. **finance**

### Pasos por plugin (mismo patrón)
1. Abrir `docs/_inbox/plugin_drop/<plugin>/1.0.0/CONNECTORS.md`.
2. Configurar credenciales de cada MCP server indicado.
3. Re-ejecutar probe:
   - `python3 scripts/plugin_connector_probe.py`
4. Validar runtime:
   - `python3 scripts/plugin_runtime_smoke.py`
5. Resultado esperado para pasar:
   - `execution.status=OK` para ese plugin
   - `auth_needed=0` y `missing_url=0` en probe

## Estado actual de lote 1
- sales: FAIL (auth pendiente)
- customer-support: FAIL (auth pendiente)
- finance: FAIL (auth pendiente + algunos missing_url)

## Evidencia actual
- `docs/_inbox/plugin_phase4_activation_matrix_latest.md`
- `docs/_inbox/plugin_drop/connector_probe_latest.json`
- `docs/_inbox/plugin_runtime_smoke_latest.md`

## Definición de terminado Fase 4
- Lote 1 en `OK` (no `OK_PARTIAL`) dentro del contrato `execution` del router.
