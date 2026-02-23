# Plugin Runtime Integration (Fase 2)

Actualizado: 2026-02-23T13:08:00-05:00

## Qué se cableó

1. **Consumo runtime real en NL router**
   - `scripts/nl_skill_router.py` ahora carga rutas desde:
     - `state/plugin_nl_routing.json`
     - `state/cc_plugin_nl_routing.json`
   - Si hay match por regex/sinónimo, planifica:
     - `route_type=workflow`
     - `selected_target=plugin.<nombre>`

2. **Registro dinámico en recipes registry**
   - `scripts/skill_recipe_registry.py` ahora inyecta recetas `plugin.*` desde:
     - `state/plugin_runtime_registry.json`
     - `state/cc_plugin_runtime_registry.json`
   - Esto evita fallback espurio a `rag.answer` por targets no registrados.

3. **Trazabilidad de dispatch plugin**
   - `plan.plugin_dispatch` en salida del router:
     - `matched`, `plugin`, `pattern`, `status`
   - Evento de observabilidad adicional:
     - `kind=plugin_route`

4. **Smoke test reproducible**
   - Nuevo script: `scripts/plugin_runtime_smoke.py`
   - Reportes:
     - `docs/_inbox/plugin_runtime_smoke_latest.json`
     - `docs/_inbox/plugin_runtime_smoke_latest.md`

## Resultado Fase 2

- Smoke actual: **12/12 PASS**.
- Muestras verificadas de salida runtime:
  - ventas -> `plugin.sales`
  - code review -> `plugin.code-review`
  - documentación API -> `plugin.context7`

## Nota de alcance

Esto deja **operativo el enrutamiento NL a plugin en planificación runtime**.
No ejecuta conectores externos por sí mismo (eso depende de credenciales/autorización por plugin).
