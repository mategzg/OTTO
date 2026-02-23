# Plugin Execution Contract (Fase 3)

Actualizado: 2026-02-23T13:12:00-05:00

## Objetivo
Convertir `plugin.*` de simple routing a ejecución con estado verificable por request.

## Implementación

1. Nuevo módulo `scripts/plugin_execution_contract.py`
   - Evalúa target `plugin.<name>` contra:
     - `state/plugin_runtime_registry.json`
     - `state/cc_plugin_runtime_registry.json`
     - `docs/_inbox/plugin_drop/connector_probe_latest.json`
   - Emite contrato:
     - `status`: `OK` | `OK_PARTIAL` | `GAP`
     - `mode`: `supercharged` | `standalone`
     - `next_action`
     - `connector_summary` (total/reachable/auth_needed/missing_url)

2. Integración en `scripts/nl_skill_router.py`
   - Después del plan, se calcula `execution` real para targets `plugin.*`.
   - Se agrega evento de observabilidad: `kind=plugin_execution`.

3. Smoke test actualizado
   - `scripts/plugin_runtime_smoke.py` valida ahora:
     - target esperado
     - estado de ejecución (`OK*` o `planned`)

## Resultado verificable

- `docs/_inbox/plugin_runtime_smoke_latest.md`:
  - **12/12 PASS**
  - SG plugins: mayormente `OK_PARTIAL` (standalone + conectores pendientes auth)
  - Plugins de código sin conectores obligatorios (ej. `code-review`, `context7`, `vercel`): `OK`

## Ejemplos reales

- Ventas -> `plugin.sales` -> `OK_PARTIAL` (auth pendiente en varios conectores)
- Code review -> `plugin.code-review` -> `OK`
- Legal/NDA -> `plugin.legal` -> `OK_PARTIAL`

## Lectura honesta

- Sí quedó operativo el **contrato de ejecución** por plugin en runtime.
- No implica que todos los conectores externos estén autenticados: eso sigue siendo fase de activación credenciales.
