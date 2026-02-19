# Card: Coder CLI — Sistema de Delegación de Código

> Fuente: workers/coder_cli.py (legacy, recuperado feb-2026)
> Ubicación actual: `workers/coder_cli.py`

## Qué hace
Sistema de delegación de tareas de código a agentes externos (Codex, Claude Code, etc.) con fallback manual.

## Arquitectura
1. **Perfiles:** `workers/coder_profiles.json` define comandos y timeouts por perfil
2. **Resolución:** env vars (`CODER_PROFILE`, `CODER_CMD`, `CODER_ARGS`) > perfil > default "manual"
3. **Ejecución:** si hay comando → subprocess con timeout; si no → manual fallback
4. **Manual fallback:** escribe prompt en `dropzone/prompts/{task_id}.md`, espera resultado en `dropzone/results/{task_id}.md`
5. **Output:** markdown con front-matter YAML (task_id, status, kind)

## Estados de retorno
- `ok` — ejecución exitosa
- `error` — falló el comando
- `needs_input` — timeout o esperando input manual

## Patrón clave
El sistema NUNCA se bloquea: si no puede ejecutar, cae a manual handoff y registra actividad. Siempre hay un path forward.

## Relevancia actual
OpenClaw ya tiene `sessions_spawn` y el skill `coding-agent` que reemplazan parte de esto. Pero el patrón de dropzone + manual fallback es útil para tareas que necesitan aprobación humana antes de ejecutar.

## Decisión
Mantener como referencia. La delegación actual usa `sessions_spawn` con Codex/Claude Code.
