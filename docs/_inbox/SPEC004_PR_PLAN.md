# SPEC-004 — PR Plan Contract (Milestone-per-PR)

Status: READY (local plan committed)
Owner: Mateo
Execution mode: Delegation-by-default, OpenClaw-native

## Program Rules (hard)

1. One milestone = one PR.
2. No blind merge; each PR must pass milestone gates before merge.
3. Keep rollback path for every PR.
4. Claims without evidence are invalid (`NO_VERIFICADO + GAPS`).
5. Customer-facing output must pass audience filter.

---

## PR-0 (M0) — Guardrails + Trust Boundaries + No-Leak

### Scope
- Multi-agent boundaries (`mateo`, `sg_frontline`, `sg_staff`, `ops`) with secure runtime policies.
- WhatsApp `dmScope` hard isolation (per account-channel-peer).
- Discord thread continuity isolation.
- Restrictive send policy for cron/hook sessions.
- Tool allow/deny policy per agent role.

### Required tests/gates
- No-leak test: two WhatsApp numbers, verify no context crossover.
- `openclaw security audit --deep` (required artifact).

### Artifacts
- Policy files + test report + audit report.

---

## PR-1 (M1) — Dispatcher + Always-Delegate + Queue Hardening

### Scope
- Dispatcher-first behavior for human-facing agents.
- Long/multi-step/tooling missions always spawn sub-agent.
- Queue collect/coalescing in WhatsApp and Discord.

### Required tests/gates
- 10-message run: ACK fast + subagent runs + no dispatcher blocking.
- Queue collect behavior validated under burst.

### Artifacts
- Latency report (ACK), subagent orchestration report, queue metrics snapshot.

---

## PR-2 (M2) — Retrieval Supreme + Evidence Contract

### Scope
- Hybrid retrieval (vector+keyword), MMR, temporal decay.
- Evidence middleware: citations or abstention.
- Audience/role-safe output policy enforcement.

### Required tests/gates
- Retrieval proof: hybrid + MMR + decay active on memory corpus.
- Auto-citations present when grounded.
- Abstention path (`NO_VERIFICADO + GAPS`) when evidence missing.

### Artifacts
- Retrieval config diff, quality metrics, citation/abstention test logs.

---

## PR-3 (M3) — Event-Driven Ingestion (Attachments + _pending)

### Scope
- Attachment ingest from Telegram/Discord/WhatsApp via ops pipeline.
- `_pending` immediate trigger (no heartbeat dependency).
- ChatGPT export parser + normalized markdown index.

### Required tests/gates
- Large Telegram attachment: autonomous ingest + indexing + QA pass.
- `_pending` trigger-to-done latency test.

### Artifacts
- Ingest report, index delta report, QA sample report.

---

## PR-4 (M4) — SharePoint Incremental Sync + Audience Tagging

### Scope
- Incremental sync (delta/modified/etag).
- Conversion to markdown (docx/pdf/html/xlsx).
- Metadata tagging (`audience`, `domain`, `doc_version`, `content_hash`).

### Required tests/gates
- Incremental re-run idempotency.
- Audience filter validation in retrieval outputs.

### Artifacts
- Sync manifest, conversion summary, retrieval safety checks.

---

## PR-5 (M5) — Odoo Deterministic Flows + Handoff Gate

### Scope
- Typed Odoo operations for lead/activity/quote/order draft.
- Deterministic workflow: lead -> quote -> order draft -> Mateo handoff.
- Side-effect safety: idempotency, retries, breaker, logging.

### Required tests/gates
- Odoo flow with Lobster approval/resumeToken handoff.
- Retry/idempotency test for side effects.

### Artifacts
- Odoo flow execution log, handoff packet example, breaker event traces.

---

## PR-6 (M6) — Skills/Plugins Intake Marketplace

### Scope
- ZIP/TGZ intake: validate -> risk score -> promote.
- Plugin/hook pack gating + approval path if sensitive.
- Skill cards (when to use / when not to use).

### Required tests/gates
- Valid + invalid skill pack scenarios.
- Relevance/safety gating and promotion decisions audited.

### Artifacts
- Intake report, promoted skill registry diff, safety review logs.

---

## PR-7 (M7) — Day-2 Autonomy (Heartbeat + Cron + Breaker)

### Scope
- Per-agent heartbeat checklist behavior.
- Cron jobs for sync/regression/maintenance.
- Circuit breaker policy enforcement across jobs/tools.

### Required tests/gates
- Heartbeat no-spam behavior.
- Cron isolation + breaker cooldown behavior verified.

### Artifacts
- Heartbeat report snapshots, cron run ledger, breaker timeline.

---

## PR-8 (M8) — Production QA Final

### Scope
- Golden set >= 50 (personal + SG scenarios).
- Regression automation.
- Final no-leak + readiness audit.

### Required tests/gates
- Golden thresholds pass.
- Final security/no-leak audit pass.

### Artifacts
- Final readiness report (`GO/NO-GO`) + rollback map.

---

## Global acceptance criteria

- Availability: ACK < 2s for dispatcher path in benchmark runs.
- No-leak: 0 verified cross-audience/cross-session leaks.
- Groundedness: all business claims have citation or abstain.
- Side effects: idempotent/retriable with breaker-protected execution.
- Operational: day-2 reports reproducible and auditable.

## Blockers to open GitHub PRs right now

1. `gh` is not authenticated in this environment.
2. No git remote configured in this workspace.

### Immediate next actions (to open PRs for real)

1. `gh auth login`
2. `git remote add origin <repo-url>` (if missing)
3. Create milestone branches `spec004/m0` ... `spec004/m8`
4. Open PRs as draft with this plan as contract and checklist.
