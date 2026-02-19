# Ingest Pipeline

## Purpose

Definir pipeline determinista para asimilar corpus: triage -> plan -> apply -> processed -> reindex.

## Use when

- Necesitas flujo oficial de ingestion universal.

## Avoid when

- No existe root canonico limpio.
- Hay stop conditions (corpus demasiado grande o tooling sospechoso).

## Routing

1. Preflight instruction surface: `python3 scripts/instruction_surface_doctor.py --scan --root /home/agente/otto-workspace` (fix si hay drift).
2. Triage: `python3 scripts/corpus_triage.py --root /home/agente/otto-workspace`
3. Plan: `python3 scripts/brain_ingest_router.py --plan --root /home/agente/otto-workspace`
4. Apply: `python3 scripts/brain_ingest_router.py --apply <plan_id> --root /home/agente/otto-workspace`
5. Reindex: `python3 scripts/brain_index_build.py`
6. Verificacion: doctor + hygiene scan.

## Maintenance

- El plan se persiste en `state/ingest_plans/<plan_id>.json`.
- Apply mueve source a `_processed` solo si estado final es success.

## Links

- `docs/_inbox/corpus_triage_latest.json`
- `docs/_inbox/corpus_assimilation_plan_latest.json`
- `docs/_inbox/corpus_assimilation_report_latest.json`
- `docs/_inbox/instruction_surface_report_latest.json`
