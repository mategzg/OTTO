# HEARTBEAT.md

Run exactly this command from the workspace root:

`python3 scripts/heartbeat_worker.py --once --root .`

If the run finishes with no pending work or blocking errors, respond:

`HEARTBEAT_OK`

Rules:
- Do not infer old tasks from prior chats.
- Process only what current policies and queues indicate.
- Keep execution bounded by `state/heartbeat_policy.json`.
- Mission clarity is mandatory: heartbeat is an execution engine, not a passive ping.
- If a pending item exists and is policy-allowed, heartbeat MUST either: (a) process it, (b) delegate it with handoff contract, or (c) emit explicit GAP/NO_VERIFICADO with blocker + next action.
- Never leave ambiguous "in_progress" states without a verifiable owner artifact (`docs/_inbox/subagent_handoffs/*.json`) or stale-reset path.

Operational behavior:
- Heartbeat performs a pre-check of queues/backlogs. If no pending work is detected, status is `no_pending_work` and response should still be `HEARTBEAT_OK`.
- Heartbeat uses `heartbeat_minimal` context profile (no heavy SOUL/memory load).
- Heartbeat delegates heavy work to coders externos via `scripts/heartbeat_delegator.py`.
- Delegated runs are considered complete only with handoff evidence file (see `state/delegation_handoff_policy.json`).
- Mission contract reference: `docs/_inbox/heartbeat_mission_contract_latest.md`.
- Delegation fallback chain: `codex` -> `claude_code` -> `telegram_owner`.
- Ingest masivo es progresivo por lotes delegados: cada ciclo toma un batch dentro de limites de policy y deja remanente para el siguiente heartbeat.
- Inline stages (always local, lightweight):
  1. reminders
  2. outbox delivery
  3. health notify (prod_doctor + safety/dead_letter signals + cooldown)
  4. housekeeping (token budget cleanup + outbox archive cleanup)
- Delegated stages (no inline execution in heartbeat):
  - ingest pipeline (`dropbox_intake` -> `chatgpt_export_normalize` -> `corpus_triage` -> `brain_ingest_router` -> `write_router`)
  - hook_backlog replay
  - research
  - odoo
  - summarizer
  - memory compact/index
  - episodic memory build
- Tratamiento de imagenes de export ChatGPT: se catalogan en `normalized/attachments.ndjson` y se archivan en `vault/inbox_raw/sources/<package>/images/` sin OCR/vision.
