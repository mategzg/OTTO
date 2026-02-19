# Prod Doctor

- Status: `ok`
- Go/No-Go: `go_with_limits`
- Checks OK: 7/8

## Checks

- ✅ `canonical_root_marker`: Canonical root pin marker must exist.
  - evidence: `.openclaw/CANONICAL_ROOT.json`
  - gap: Falta .openclaw/CANONICAL_ROOT.json
- ✅ `heartbeat_contract`: Heartbeat contract should call heartbeat_worker once.
  - evidence: `HEARTBEAT.md`
  - evidence: `scripts/heartbeat_worker.py`
  - gap: HEARTBEAT.md no contiene contrato operativo esperado.
- ✅ `heartbeat_policy_interval`: interval_minutes should remain 30 for passive cadence.
  - evidence: `state/heartbeat_policy.json`
  - gap: state/heartbeat_policy.json interval_minutes != 30
- ✅ `openclaw_cli_present`: openclaw CLI detected at /home/agente/.npm-global/bin/openclaw
- ✅ `openclaw_cli_help`: openclaw --help executed.
  - gap: openclaw --help rc=0
- ✅ `openclaw_hooks_help`: hooks command availability probe.
  - evidence: `hooks/otto-runtime-bridge/HOOK.md`
  - gap: openclaw hooks --help rc=0
- 🟨 `hook_bridge_discovery`: Attempt to verify hook discovery through openclaw hooks list.
  - evidence: `hooks/otto-runtime-bridge/HOOK.md`
  - evidence: `hooks/otto-runtime-bridge/handler.js`
  - gap: GAP/NO VERIFICADO: hook bridge no confirmado por openclaw hooks list.
- ✅ `outbox_scan`: outbox scan completed (dry non-delivery).
  - evidence: `docs/_inbox/outbox_delivery_report_latest.json`
  - evidence: `docs/_inbox/outbox_delivery_report_latest.md`
