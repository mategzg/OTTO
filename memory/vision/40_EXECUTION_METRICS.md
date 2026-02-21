# 40 — Execution Metrics

Metrics validate reality; they do not define strategy.

## M1 — Reliability
- Runtime health stable (critical checks green).
- Regression rate controlled.
- Recovery path tested for high-risk flows.

## M2 — Flow Quality
- Backlog aging bounded.
- Queue hygiene maintained (no persistent dirty states).
- Handoff completion latency within target.

## M3 — Efficiency
- Context/token cost per completed unit trending down or stable.
- Rework ratio bounded.
- Manual intervention rate decreases in repeatable tasks.

## M4 — Decision Effectiveness
- Decisions linked to explicit evidence.
- Next actions are concrete and owner-assigned.
- Post-decision outcome review performed on material items.

## Metric governance
If a metric improves while user value declines, treat metric as mis-specified and recalibrate.
