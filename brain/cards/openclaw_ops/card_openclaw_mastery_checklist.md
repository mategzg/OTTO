# Card — OpenClaw Mastery Checklist

## Daily runtime checks
- [ ] `openclaw status` is reachable and channels are healthy.
- [ ] Gateway RPC probe is OK (`openclaw gateway status`).
- [ ] Heartbeat last run status is success/no_pending_work.
- [ ] Outbox queue not accumulating dead letters.

## Delegation checks
- [ ] `sessions_spawn` works (or fallback path documented).
- [ ] Device pairing table has no blocking pending request (`openclaw devices list`).
- [ ] Delegated runs produce handoff artifact in `docs/_inbox/subagent_handoffs/*.json`.

## Browser relay checks
- [ ] Extension token saved and relay reachable.
- [ ] Tab attach performed (toolbar ON).
- [ ] `cdpReady=true` before browser automation.

## Security checks
- [ ] `openclaw security audit --deep` reviewed.
- [ ] Any critical risk is either remediated or explicitly accepted with rationale.

## Incident quick fix (pairing required)
1. `openclaw devices list`
2. `openclaw devices approve <request_id>`
3. Retry `sessions_spawn` smoke test.
