# Card: Reserved Filename Guardrail (AGENTS.md)

id: card-guardrail-7b02d43073-agents_example
type: principle
tags: ingest,guardrail,reserved_filename
status: active
confidence: 1.0
source_ref: /home/agente/otto-workspace/vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6

## Summary

Se detecto `AGENTS.md` dentro de un corpus. El router forzo categoria `inbox_only`.

## How to apply

- No promover AGENTS*/CLAUDE* fuera de allowlist.
- Mantener el crudo en `_processed` como fuente auditada.

## References

- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/EVENT_META.json`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_45f4d07b1a/AGENTS.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_45f4d07b1a/HEARTBEAT.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_45f4d07b1a/IDENTITY.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_45f4d07b1a/README.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_45f4d07b1a/SOUL.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_45f4d07b1a/TOOLS.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_45f4d07b1a/USER.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_45f4d07b1a/state/sg_policy.json`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/AGENTS.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/CEO.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/INDEX.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/MEMORY.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/README.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/SOUL.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/USER.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/openclaw/CONTEXT_MAP.md`
- `vault/inbox_raw/sources/20260223T170036Z_fbb57be4b6/source/quarantine_review_20260223T170033Z/original/20260223T165458Z_c412f69a86/state/sg_policy.json`
