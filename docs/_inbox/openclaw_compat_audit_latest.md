# OpenClaw Compatibility Audit

- Canonical root: `/home/agente/otto-workspace`
- Created at: `2026-02-19T02:21:31.389206+00:00`
- Status: `ok`
- Go/No-Go: `go_with_limits`

## Compatibility Matrix

| Area | Verdict | Notes |
| --- | --- | --- |
| Workspace semantics | ✅ `compatible` | Raiz canonica pinneada y contexto operativo en repo. |
| Hooks (message received/sent) | 🟨 `risk` | Bridge de workspace hook existe y enruta a ingress adapter. |
| Heartbeat behavior | ✅ `compatible` | Heartbeat ejecuta pipeline pasivo por bloques sin requerir comandos del usuario. |
| Cron vs Heartbeat | 🟨 `risk` | Repo documenta uso de heartbeat; no hay verificacion automatizada de contrato cron OpenClaw en este run. |
| Sessions/session scoping (zero-mix) | ✅ `compatible` | Session_id usa canal/account/peer/channel/thread para aislamiento por chat/thread. |
| Subagents / multi-agent compatibility | 🟨 `risk` | Delegacion y lectura base estan definidas; falta verificacion e2e con orchestration externa de sub-agents. |
| Delegation + instruction surface control | ✅ `compatible` | Allowlist de archivos reservados y doctor de drift activos. |
| Hygiene + repo reality posture | ✅ `compatible` | Doctors deterministas presentes para limpieza/no-drift. |

## Evidence by Area

### Workspace semantics
- Verdict: `compatible`
- Evidence: `.openclaw/CANONICAL_ROOT.json`
- Evidence: `openclaw/CONTEXT_MAP.md`
- Evidence: `scripts/repo_root.py`

### Hooks (message received/sent)
- Verdict: `risk`
- Evidence: `hooks/otto-runtime-bridge/HOOK.md`
- Evidence: `hooks/otto-runtime-bridge/handler.js`
- Evidence: `scripts/channel_ingress_adapter.py`
- GAP/NO VERIFICADO: Hook marcado experimental; recomendable validacion en entorno productivo OpenClaw.

### Heartbeat behavior
- Verdict: `compatible`
- Evidence: `HEARTBEAT.md`
- Evidence: `scripts/heartbeat_worker.py`
- Evidence: `state/heartbeat_policy.json`

### Cron vs Heartbeat
- Verdict: `risk`
- Evidence: `AGENTS.md`
- Evidence: `HEARTBEAT.md`
- Evidence: `scripts/heartbeat_worker.py`
- GAP/NO VERIFICADO: GAP/NO VERIFICADO: contrato oficial cron vs heartbeat no validado en runtime real.

### Sessions/session scoping (zero-mix)
- Verdict: `compatible`
- Evidence: `scripts/channel_ingress_adapter.py`
- Evidence: `scripts/session_memory_manager.py`
- Evidence: `state/channel_runtime_policy.json`

### Subagents / multi-agent compatibility
- Verdict: `risk`
- Evidence: `.claude/rules/00_CANON.md`
- Evidence: `AGENTS.md`
- Evidence: `CLAUDE.md`
- Evidence: `brain/domains/openclaw_ops/07_DELEGATION_POLICY.md`
- GAP/NO VERIFICADO: GAP/NO VERIFICADO: flujo multi-agent externo no validado en este entorno.

### Delegation + instruction surface control
- Verdict: `compatible`
- Evidence: `docs/_inbox/instruction_surface_report_latest.json`
- Evidence: `scripts/instruction_surface_doctor.py`
- Evidence: `state/instruction_surface_policy.json`

### Hygiene + repo reality posture
- Verdict: `compatible`
- Evidence: `docs/_inbox/repo_reality_report_latest.json`
- Evidence: `docs/_inbox/workspace_hygiene_report_latest.json`
- Evidence: `scripts/repo_reality_doctor.py`
- Evidence: `scripts/workspace_hygiene_doctor.py`

## GAPS/NO VERIFICADO

- GAP/NO VERIFICADO: contrato oficial cron vs heartbeat no validado en runtime real.
- GAP/NO VERIFICADO: flujo multi-agent externo no validado en este entorno.
- Hook marcado experimental; recomendable validacion en entorno productivo OpenClaw.

## Context Snapshot

- `?? .gitignore`
- `?? .openclaw/`
- `?? AGENTS.md`
- `?? BOOT.md`
- `?? BOOTSTRAP.md`
- `?? CEO.md`
- `?? CLAUDE.md`
- `?? COMMAND_LOGGER.md`
- `?? HEARTBEAT.md`
- `?? IDENTITY.md`
- `?? INDEX.md`
- `?? PROJECT_BRIEF.md`
- `?? README.md`
- `?? REPO_MAP.md`
- `?? SESSION_MEMORY.md`
- `?? SOUL.md`
- `?? TOOLS.md`
- `?? USER.md`
- `?? brain/`
- `?? copilots/`
- `?? dashboard/`
- `?? dashboard_server.py`
- `?? docs/`
- `?? hooks/`
- `?? hq_logging.py`
- `?? index_docs.py`
- `?? logs/`
- `?? memory/`
- `?? openclaw/`
- `?? ops/`
- `?? otto_state.py`
- `?? plans/`
- `?? pytest.ini`
- `?? repo_map/`
- `?? requirements.txt`
- `?? scripts/`
- `?? state/`
- `?? templates/`
- `?? tests/`
- `?? vault/`
- `?? workers/`
