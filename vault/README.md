# Vault — Purged 2025-06-21

Legacy vault content was fully processed and purged.

## What was here
- `_salvage/` — ~15 timestamped snapshot dirs (122MB, heavily duplicated)
- `_quarantine/` — 3 categories: bad_path_roots, home_junk, old_backups (7MB)
- `inbox_raw/` — pending/processed ingestion bundles (1.5MB)
- Total: 130MB, ~16,000 files

## What was extracted
All unique knowledge distilled into brain cards:
- `brain/cards/` — 6 cards (architecture, session memory, otto hq v1, odoo, coder delegation, legacy scripts)
- `brain/domains/sg_acabados/` — 4 cards (delegation, legal peru, odoo ops, runbooks)
- `brain/domains/legacy/POLICY.md` — legacy handling policy

Recovered scripts:
- `scripts/odoo/odoo_bulk_import.py` + tests
- `workers/coder_cli.py`

## Recovery state
See `state/legacy_recovery_state.json` and `state/legacy_gap_report.json` for full audit trail.

## Backup
Moved to `/tmp/vault_*_purged/` (ephemeral, cleared on WSL restart).
