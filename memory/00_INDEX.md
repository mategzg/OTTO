# MemoryOS Index

MemoryOS stores human memory as structured records with `source_ref` evidence.

## Workflow

1. Capture append-only into `docs/_inbox/memory_inbox.ndjson`.
2. Compact/promote into canonical `memory/*.ndjson`.
3. Build search index in `state/memory_index.json`.
4. Query via `scripts/memory_query.py` or `/memory ask ...`.

## Rules

- No direct manual edits to canonical NDJSON streams.
- No expiry by age. Records stay active until superseded by better-known evidence.
- Every promoted record must keep `source_ref`.

## Canonical Streams

- `memory/03_PREFERENCES.ndjson`
- `memory/04_PROJECTS.ndjson`
- `memory/05_DECISIONS.ndjson`
- `memory/06_TIMELINE.ndjson`
