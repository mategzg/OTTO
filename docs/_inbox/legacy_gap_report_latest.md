# Legacy Gap Report v2

- Canonical root: `/home/agente/otto-workspace`
- Version: `2`
- Compared: 8227
- Missing (raw): 7673
- Missing unique: 26
- Suppressed duplicates: 672
- Suppressed path noise: 5188
- Excluded artifacts: 1787
- Bucket by type: `{"code": 4, "doc": 7, "runtime": 15}`
- JSON report: `docs/_inbox/legacy_gap_report_latest.json`
- Log report: `logs/legacy_gap_report_latest.json`

## Why prior top20 was noise

- Se suprimieron 5188 candidatos por path_noise (bad_path_roots/nested/windows repetido).
- Se excluyeron 1787 artefactos de ejecución (docs/_inbox, logs, ops, copilots, state latest/report).
- Se suprimieron 672 duplicados por canonical_coldstore_key/content_hash.

## Top Missing Unique Candidates (max 50)

- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/openclaw/CONTEXT_MAP.md` | type=runtime | score=511 | key=64fbe53eba1b8a873b
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/scripts/autonomy_tick.py` | type=code | score=502 | key=87892c61fac1d4ee29
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/scripts/repo_reality_doctor.py` | type=code | score=419 | key=3e50967b0f43f58531
- `vault/_salvage/20260218T041520Z_a6d6e4e9ff/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/scripts/repo_reality_doctor.py` | type=code | score=419 | key=8b9d867f5d557d3fe7
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/SOUL.md` | type=runtime | score=410 | key=93f9aea8ad8372cb3e
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/tests/test_openclaw_hook_repo_commands.py` | type=runtime | score=311 | key=8c2c904f3a0956e858
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/C:\Users\sgaca\SG Acabados\AGENTE OTTO/SOUL.md` | type=runtime | score=310 | key=857301a75c3c584f7d
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/SESSION_MEMORY.md` | type=runtime | score=310 | key=3cbf707f5aed78a13a
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/docs/empresa/ROUTER.md` | type=runtime | score=310 | key=8b8fde81ef2ff6c3cf
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/INDEX.md` | type=runtime | score=310 | key=2f353dd126a641fcbe
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/openclaw/00_INDEX.md` | type=runtime | score=310 | key=95047b17d2f61b0a41
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/scripts/odoo/odoo_bulk_import.py` | type=code | score=304 | key=03f0945c7293c0a9dd
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/docs/empresa/index.md` | type=doc | score=240 | key=96d47dd13677207306
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/plans/2026-02-11-otto-hq-v1.md` | type=doc | score=240 | key=2c93087bbec472e365
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/workers/coder_cli.py` | type=runtime | score=215 | key=ff9e0224f1492c160f
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/C:\Users\sgaca\SG Acabados\AGENTE OTTO/IDENTITY.md` | type=runtime | score=210 | key=2fb3fee390c67ed9a8
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/IDENTITY.md` | type=runtime | score=210 | key=b6d8cfe41673d6a471
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/CEO.md` | type=runtime | score=210 | key=d2051ba66d617ade0f
- `vault/_salvage/20260218T041520Z_d70c621560/staged/IDENTITY.md` | type=runtime | score=210 | key=19e88f980ca1c50b2a
- `vault/_salvage/20260218T041520Z_d70c621560/staged/SOUL.md` | type=runtime | score=210 | key=62d6f46a6668b68d42
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/BOOTSTRAP.md` | type=doc | score=140 | key=e79c56add8977bff7c
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/C:\Users\sgaca\SG Acabados\AGENTE OTTO/HEARTBEAT.md` | type=doc | score=140 | key=01e88042b365b36364
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/C:\Users\sgaca\SG Acabados\AGENTE OTTO/TOOLS.md` | type=doc | score=140 | key=86a0049563f424a7f0
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/HEARTBEAT.md` | type=doc | score=140 | key=b70d52a80e76fe4ed7
- `vault/_quarantine/old_backups/20260218T025933Z_6fb9ed08bb/docs/empresa/memory.md` | type=doc | score=140 | key=5b2fc68841fbc64613
- `vault/_salvage/20260218T025727Z_5c1adbab14/staged/C:\Users\sgaca\SG Acabados\AGENTE OTTO/vault/README.md` | type=runtime | score=90 | key=cd624128a761d7920d
