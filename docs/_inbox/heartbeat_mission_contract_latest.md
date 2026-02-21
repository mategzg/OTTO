# Heartbeat Mission Contract (No Ambiguity)

## Purpose
Heartbeat is responsible for moving pending work to verified closure, not just running periodic checks.

## Allowed outcomes per pending item
1. **Processed inline** (with report evidence), or
2. **Delegated with owner artifact** (`docs/_inbox/subagent_handoffs/*.json`) and supervisor acknowledgment, or
3. **Blocked explicitly** (`GAP/NO_VERIFICADO` + blocker + next action).

Any other state is invalid for closure.

If delegated run ends without handoff artifact, classify as failed attempt, report blocker, fix root cause, then retry (no blind auto-retry).

## Non-negotiables
- No ambiguous active lock without verifiable owner path.
- No silent backlog drift.
- No fake completion without gates/evidence.
- Delegated phase work must be supervised by subagent loops that wait for coder handoff signal before reporting completion.
- One subagent per phase; no cross-phase mixing inside a single supervisor mission.

## Escalation trigger
If pending/failing items persist across cycles without ownership evidence, escalate as alert (not HEARTBEAT_OK).
