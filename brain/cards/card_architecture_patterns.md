# Card: Patrones de Arquitectura (Legacy Destilado)

> Fuente: CEO.md, CLAUDE.md, BOOT.md, COMMAND_LOGGER.md, DROPZONE_CONTRACT.md, TOOLS.md, MemoryOS report (legacy)
> Dominio: arquitectura / operaciones

## Capas de Autoridad (patrón vigente)
1. Canon: CEO.md
2. Contexto: openclaw/CONTEXT_MAP.md
3. Hub humano: INDEX.md
4. Hub brain: brain/00_INDEX.md
5. Wrappers: SOUL.md, AGENTS.md (no duplicar canon en wrappers)

## Guardrails Universales
1. No inventar (flags, comandos, datos)
2. No borrar
3. No reordenar masivamente

## Logging Estandarizado
```json
{"ts":"ISO8601Z","level":"info|warning|error","event":"...","detail":"...","task_id":"...","channel":"telegram|whatsapp|manual"}
```
- Nunca incluir secretos/tokens
- task_id preferido cuando exista misión

## Secuencia de Boot (referencia)
1. Garantizar estructura: state/, logs/, plans/, dropzone/, docs/
2. Indexar docs
3. Setear estado inicial
4. No abrir web automáticamente

## Dropzone Contract (patrón file-based delegation)
- Prompts: `dropzone/prompts/<task_id>.md` con YAML front-matter
- Results: `dropzone/results/<task_id>.md` con mismo formato
- Status: ok | error | needs_input
- Reemplazado por sessions_spawn en la versión actual, pero el patrón de handoff con front-matter es reutilizable.

## Sanitización de Secretos en Logs
Patrón de hq_logging.py — regex automático para redactar:
- `sk-[A-Za-z0-9_-]{8,}` (API keys)
- `api[_-]?key\s*[:=]\s*[^\s,;]+`
- `token\s*[:=]\s*[^\s,;]+`
Siempre sanitizar antes de loguear. Nunca secretos en claro.

## Lección Clave del MemoryOS
El workspace anterior tenía un root pinneado en path Windows inválido (`C:\Users\sgaca\...`) que generó copias recursivas infinitas. El sistema de quarantine resolvió esto pero dejó deuda técnica masiva en el vault. Lección: **siempre validar que el canonical root sea un path limpio antes de operar.**
