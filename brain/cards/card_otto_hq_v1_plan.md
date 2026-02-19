# Card: Otto HQ v1 — Plan Original

> Fuente: plans/2026-02-11-otto-hq-v1.md (legacy)
> Estado: Parcialmente superseded por migración a OpenClaw 2026.2.14

## Qué era
Plan para construir la base operativa de Otto con:
- Dashboard local (Python stdlib)
- Scripts: `otto_state.py`, `dashboard_server.py`, `index_docs.py`
- Estado/kanban/logs como archivos
- Delegación file-based (dropzone)
- Tests pytest (≥4)
- Windows-first

## Qué se cumplió
- ✅ Estructura de carpetas
- ✅ Scripts de delegación (coder_cli.py)
- ✅ Docs empresa (ROUTER, memory, index)
- ✅ Tests

## Qué cambió
- Dashboard local → reemplazado por OpenClaw Control UI
- otto_state.py → reemplazado por heartbeat_worker.py
- index_docs.py → reemplazado por project_docs_maintainer
- Windows-first → migrado a WSL2 Linux
- File-based delegation → reemplazado por sessions_spawn

## Lección
El plan era sólido. La migración a OpenClaw absorbió la mayoría de funciones. Lo que queda útil son los patrones de diseño (plan-first, safety flags, file-based fallback).
