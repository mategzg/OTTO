# 60 - Delegation Doctrine

## Delegate When (MUST)
- Work is multi-stage, long-running, or blocks primary throughput.
- Validation requires broad file/test coverage.
- Research depth exceeds efficient inline execution.

## Strategy Selection (MUST)
- Choose autonomously per mission: direct local execution, single delegation + coder, parallel delegations, or supervised iterative delegation.
- For complex missions, prefer supervisor loop: prompt -> coder result -> verify -> next prompt, until closure.
- Optimize for throughput + reliability + token efficiency, not just speed.
- For phased pipelines, enforce **one supervisor subagent per phase**; never mix multiple phases inside the same supervisor loop.
- Parallelism is allowed only as "N phases => N supervisors", each with isolated scope and its own handoff path.

## Keep Local When
- Scope is small, deterministic, and faster end-to-end locally.
- Delegation overhead would exceed execution cost.

## Delegation Contract (required)
- Scope includes and exclusions (explicit paths).
- Non-goals to prevent drift.
- Validation gates and expected proof.
- Required handoff artifact path and format.

## Routing Rule
- Default coder: Codex.
- Use Claude Code only when work depends on `.claude/*`, Claude plugins, or Claude import/rule behavior.

## Failure Triage
1. Auth/pairing/permissions.
2. Missing contract details.
3. Stale lock or dead session.
4. Re-emit with corrected constraints or execute locally.

## Closure Rule
No DONE without valid handoff artifact plus gate verification.
