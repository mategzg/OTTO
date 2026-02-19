# 50 Hooks OpenClaw

Lectura minima:

1. `hooks/otto-runtime-bridge/HOOK.md`
2. `hooks/otto-runtime-bridge/handler.js`
3. `scripts/channel_ingress_adapter.py`

Notas:

- Hook bridge captura `message:received` y `message:sent`.
- Bridge esta marcado experimental; runtime canonico vive en scripts/policies del workspace.
- Compatibilidad OpenClaw documentada en `openclaw/CONTEXT_MAP.md`.
