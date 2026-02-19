# Card: Run Ledger Convention

id: card-openclaw-run-ledger-001
type: procedure
tags: run,ledger,evidence
source_ref: ops/RUN_LEDGER.ndjson; scripts/copilot_report.sh
status: active
confidence: 0.94
last_confirmed_at: 2026-02-18

## Summary

Cada run cierra con una linea en `ops/RUN_LEDGER.ndjson` y un reporte en `copilots/OpenClaw-MemoryOS_latest.md`.

## How to apply

1. Ejecutar gates reales.
2. Append de una linea NDJSON con seq/run_id/result/summary.
3. Ejecutar `scripts/copilot_report.sh` con evidence paths.
