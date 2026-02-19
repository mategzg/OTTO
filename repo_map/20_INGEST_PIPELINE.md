# 20 Ingest Pipeline

Lectura minima:

1. `scripts/dropbox_intake.py`
2. `scripts/chatgpt_export_normalize.py`
3. `scripts/corpus_triage.py`
4. `scripts/brain_ingest_router.py`

Flujo:

- `vault/inbox_raw/_pending_drop` -> intake a `vault/inbox_raw/sources/*`.
- Normalizacion (si aplica) y slicing para cargas grandes.
- Triage genera señal/plan.
- Plan/apply crea derivados (brain/cards/memory inbox) y mueve processed.
