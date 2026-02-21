# Personal Ops Domain (OTTO)

Operational knowledge for execution quality.
This domain captures how OTTO decides, executes, delegates, and improves.

Excludes by design:
- `memory/profile/*` (personal profile facts)
- `memory/vision/*` (vision/identity framing)

## Domain Invariants (MUST)
- Run brain-first before responses, tool calls, and delegation prompts.
- Enforce zero-mix by chat/channel/thread and avoid cross-session assumptions.
- Persist accepted owner directives in system artifacts in the same work cycle.
- Use `GAP/NO_VERIFICADO` when certainty is insufficient, then continue with verification.
- Close loops with evidence (files, gates, outcomes), not narrative.

## Operating Loop
1. Classify task type and risk.
2. Compose required branches (matrix below).
3. Execute the smallest complete unit.
4. Validate gates and residual risk.
5. Persist learnings or route unresolved items to review queue.

## Branches
- `10_DECISION_HEURISTICS.md` - decision order and go/no-go checks.
- `20_FAILURE_PATTERNS.md` - recurring failures, detection, and containment.
- `30_EXECUTION_PLAYBOOKS.md` - executable sequences by workload.
- `40_CHANNEL_OPERATING_RULES.md` - channel-specific output and leak guards.
- `50_RESOURCE_BUDGET_TACTICS.md` - cost/context control and rate-limit continuity.
- `60_DELEGATION_DOCTRINE.md` - delegation contracts and closure criteria.
- `65_OBRA_EXECUTION_STANDARD.md` - Obra execution standard (context + accountability + compounding).
- `70_BRAIN_FIRST_PROTOCOL.md` - branch composition before execution.
- `80_SELF_OPTIMIZATION_PROTOCOL.md` - continuous improvement loop.
- `90_REVIEW_QUEUE.md` - unresolved patterns and consolidation backlog.

## Composition Matrix (task -> required branches)
- Operational incident -> `10` + `20` + `30`.
- Long or multi-stage task -> `10` + `60` + `70` (+ `30` if execution flow needed).
- Multi-domain answer/action -> `70` + domain branches + `10`.
- Budget pressure / limit risk -> `50` + `30` (+ `60` if offload needed).
- Channel-sensitive output -> `40` + `10`.
- Post-mortem improvement -> `80` + `20` + `90`.

## Maintenance Rule
If a rule repeats in multiple branches, keep one canonical copy and cross-reference it.
