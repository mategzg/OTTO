# BOOT

Secuencia de arranque de sesion:

1. Garantizar estructura base:
   - `state/`, `logs/`, `plans/`, `dropzone/`, `docs/`
2. Ejecutar `python index_docs.py`.
3. Setear estado inicial:
   - `python otto_state.py set-status idle --task "Online, listo"`
4. No abrir web automaticamente.
