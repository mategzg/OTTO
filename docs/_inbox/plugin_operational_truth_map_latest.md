# Plugin/Skills Truth Map (Fase 1)

Actualizado: 2026-02-23T13:05:00-05:00

## Veredicto duro (sin humo)

Estado actual por capa:

1. **CATALOGADO** ✅
   - Existe inventario y metadata de plugins/skills en `docs/_inbox/plugin_drop/*`.
   - Existen registros derivados en `state/plugin_runtime_registry.json` y `state/cc_plugin_runtime_registry.json`.

2. **RUTEADO (DECLARATIVO)** ⚠️
   - Existen reglas de routing NL en `state/plugin_nl_routing.json` y `state/cc_plugin_nl_routing.json`.
   - Estas reglas están definidas como datos, pero no hay evidencia de consumo por el runtime principal.

3. **EJECUTABLE EN PIPELINE DE INGESTA** ✅
   - Hay scripts que procesan y certifican catálogos:
     - `scripts/plugin_drop_processor.py`
     - `scripts/cc_plugin_ingest.py`
     - `scripts/plugin_connector_probe.py`
     - `scripts/cc_plugin_certify.py`

4. **OPERATIVO EN RUNTIME PRINCIPAL** ❌ (GAP)
   - Búsqueda de referencias de consumo de `plugin_*registry` / `*_nl_routing` en runtime principal: **sin evidencia**.
   - Hallazgo: las referencias aparecen en scripts de procesamiento/certificación, no en un orquestador de ejecución productiva.

## Evidencia mínima

- Inventario/drop presente:
  - `docs/_inbox/plugin_drop/inventory_latest.json`
  - `docs/_inbox/plugin_drop/activation_plan_latest.md`
  - `docs/_inbox/plugin_drop/connector_probe_latest.json`
- Registros de runtime declarativo:
  - `state/plugin_runtime_registry.json`
  - `state/cc_plugin_runtime_registry.json`
  - `state/plugin_nl_routing.json`
  - `state/cc_plugin_nl_routing.json`
- Uso detectado en código:
  - `scripts/plugin_drop_processor.py:12,14`
  - `scripts/cc_plugin_ingest.py:14,15`
  - `scripts/cc_plugin_certify.py:9,10`
  - `scripts/plugin_connector_probe.py:13,14`

## Conclusión operacional

Hoy puedo afirmar con verdad:

- **Sí**: plugins/skills están importados, inventariados y con routing declarativo.
- **No**: no está verificado que estén cableados al flujo de decisión/ejecución principal en producción.

## Siguiente fase propuesta (Fase 2)

Objetivo: pasar de "catalogado/ruteado" a "ejecutado en runtime".

1. Definir punto único de consumo runtime para `plugin_nl_routing`/`cc_plugin_nl_routing`.
2. Integrar selección de plugin en el flujo NL principal.
3. Agregar trazas de decisión (input intent -> plugin elegido -> acción ejecutada).
4. Correr smoke tests NL reproducibles y dejar reporte PASS/FAIL por plugin.
