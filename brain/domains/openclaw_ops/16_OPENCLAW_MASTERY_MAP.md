# 16 OpenClaw Mastery Map

## Scope
Operational map for running OpenClaw reliably in this workspace.

## Core areas
1. Runtime ingress: `scripts/channel_ingress_adapter.py` + `repo_map/10_RUNTIME_INGRESS.md`.
2. Heartbeat/delegation: `scripts/heartbeat_worker.py`, `scripts/heartbeat_delegator.py`, `state/heartbeat_policy.json`.
3. Gateway control: `openclaw gateway *` (`status/start/stop/restart/probe/install`).
4. Browser relay: `openclaw browser *` + extension attach/token + `cdpReady` verification.
5. Models/auth: `openclaw models *` (`status`, `auth`, `set`, `fallbacks`).
6. Sessions/subagents: use `sessions_spawn` when available; if fails, diagnose pairing/device auth first.
7. Security posture: `openclaw security audit --deep` + explicit risk acceptance policy.
8. Policies/state: `repo_map/60_POLICIES_STATE.md` + runtime state files in `state/*`.

## Failure signatures and first response
- `gateway closed (1008): pairing required` -> check/approve `openclaw devices list/approve`.
- Browser relay reachable but not working -> verify extension token + attach tab + `cdpReady=true`.
- Delegation appears active with no progress -> check handoff artifact and stale lock guards.

## Verified command bundle
- `openclaw status`
- `openclaw doctor --fix`
- `openclaw gateway status`
- `openclaw devices list`
- `openclaw security audit --deep`
- `openclaw browser status --profile chrome`

## GAP / NO_VERIFICADO
- Full deep-dive for every online docs section (nodes/canvas internals) pending dedicated online crawl.
